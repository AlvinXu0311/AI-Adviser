# Architecture

This is the design reference behind the [README](README.md): how a request flows, where state
lives, what each security control defends against, how the system behaves when a dependency fails,
and why it is built this way. Diagrams: [system design](docs/diagrams/system-design.svg) and
[agent design](docs/diagrams/agent-design.svg).

## Goals

- **Correct answers from authoritative data.** Program and course facts come from SQLite; the PDF
  catalogs only fill gaps. The agent may not invent courses.
- **Safe with student records.** Transcripts are personal education records. They stay scoped to
  their owner, are encrypted at rest, are not logged, and the model sees as little as possible.
- **Operable.** Stateless application processes, every dependency with a timeout, rebuilds that
  never take retrieval down, and traces that explain an answer.

Non-goals: writing back to university systems, storing chat history beyond its TTL, or serving
users outside the configured Azure AD tenant (except the opt-in demo account).

## Components

| Component | Responsibility | Code |
|-----------|----------------|------|
| nginx (frontend container) | TLS, HSTS, CSP, static React build, `/api` proxy (SSE unbuffered), sign-in rate limit, ACME webroot, cert reload | `frontend/nginx/` |
| FastAPI backend (2 workers) | Auth, guards, chat orchestration, transcript intake, admin | `backend/app/` |
| Intent agent | Is the question academic? Retries, then fails open | `agents/intent_agent.py` |
| LangGraph adviser | `agent ⇄ tools` loop with 7 tools, 8-round budget | `agents/adviser_agent.py`, `agents/tools.py` |
| search_service | SQLite → vectors → query variations | `services/search_service.py` |
| Vector index | Read-only serving with hot swap; offline versioned builds | `services/pdf_vector_service.py`, `services/vector_index.py` |
| Redis | All mutable state (see [State model](#state-model)) | `services/conversation_memory.py`, `context_manager.py`, `session_access.py`, `rate_limit.py`, `auth.py` |
| certbot (production) | Let's Encrypt issuance and renewal | `docker-compose.prod.yml`, `scripts/init-letsencrypt.sh` |
| MCP server | Same retrieval for external MCP clients, read-only, own venv | `backend/mcp_server/` |

## Request lifecycle: one chat turn

1. **Edge.** nginx terminates TLS and proxies `POST /api/chat` with buffering off. It overwrites
   `X-Forwarded-For` with the client address it resolved (trusting only `TRUSTED_PROXY_CIDR`), so
   clients cannot spoof their IP.
2. **Body-size guard** (ASGI middleware). Rejects bodies over the limit from `Content-Length` and,
   for chunked uploads, by counting bytes as they arrive (413).
3. **Authentication.** Token from the `adviser_session` cookie (or a Bearer header). Cookie-based
   writes must carry `X-Requested-With`; the token's signature, expiry and `jti` denylist are
   checked (401 / 403).
4. **Rate limits.** Per-user budgets: 10 chat turns per minute, 300 per day (429 with `Retry-After`).
5. **Session ownership.** The session id is claimed by the first user who uses it (`SET NX`); any
   other user gets 403.
6. **Context.** Recent turns and the rolling summary from Redis; the encrypted transcript, if any.
7. **Intent.** One LLM call; on failure one retry, then fail open as academic. Non-academic
   questions get a canned reply and stop here.
8. **Adviser.** The LangGraph run streams `agent_action`, `tool_start`, `tool_end`, `token` and
   `agent_finish` events into an SSE queue. The whole run has a 120 s deadline; each Gemini call
   has 60 s and up to 3 backoff retries.
9. **Finish.** The answer is appended to history, latency recorded, a `final` event (with the
   LangSmith `trace_id`) sent, and compaction scheduled in the background.

If the browser disconnects at any point, Starlette closes the stream generator, whose `finally`
cancels the agent task, so no further LLM calls are made for an abandoned turn.

## Transcript intake

1. Ownership of the target session is checked (403 before anything else).
2. The upload must be valid base64 of a file starting with `%PDF-` and within `MAX_TRANSCRIPT_MB`.
3. Gemini reads the PDF to text, then a second call structures it into JSON (both in worker
   threads, with timeouts and retries; traced with sizes only).
4. `sanitize_transcript` keeps only validated fields: course codes, grades and terms must match
   strict patterns or are dropped; course and program names lose control and markup characters
   and are length-capped; GPA and credits are range-checked; the raw OCR text is discarded.
5. The result is stored Fernet-encrypted in Redis with the session TTL.

## State model

All mutable state is in Redis, which has a password, no host port and `maxmemory` with
`volatile-lru` eviction. Every key has a TTL.

| Key | Content | TTL | Written by |
|-----|---------|-----|------------|
| `message_store:{session}` | Chat messages | 24 h, refreshed | chat |
| `chat_summary:{session}` | Rolling summary of compacted turns | 24 h | compaction |
| `chat_compaction_lock:{session}` | Single-writer lock for compaction | 60 s | compaction |
| `student_context:{session}` | Sanitized transcript, Fernet-encrypted | 24 h, sliding | transcript intake |
| `session_owner:{session}` | Owning user id | 24 h, refreshed | first use of a session |
| `revoked_token:{jti}` | Denylisted token | until the token's expiry | logout |
| `ratelimit:{scope}:{user}` | Fixed-window counter | window length | rate limiter |
| `ratelimit:login-fail:{email\|ip}:…` | Failed demo logins | lockout length | demo login |
| `metrics:chat_latency_ms` | Recent end-to-end latencies | none (capped list) | chat |

Read-only data lives in the `./database` volume: `bus_school.db`, the catalog PDFs and
`vector_index/` (versions plus the `CURRENT` pointer).

## Security model

| Threat | Control |
|--------|---------|
| Unauthenticated access to the API or admin operations | Backend-issued JWTs on every route but health and sign-in; admin routes need a role from `ADMIN_EMAILS` |
| Forged identity from Azure AD | ID token verified against the tenant JWKS: signature, `aud`, `iss`, `tid`, email domain |
| Token theft through XSS | Token only in an HttpOnly cookie; strict CSP (`script-src 'self'`, no inline script or style, no eval) |
| CSRF | SameSite=Strict cookie plus a required custom header on cookie-authenticated writes |
| Stolen token after logout | `jti` denylist in Redis until expiry |
| Reading or deleting another user's chat (IDOR) | Sessions bound to their owner; random UUID ids |
| Student data leaking | Encrypted at rest, raw OCR text dropped, counts-only logging, model never given name or ID, redacting LangSmith client |
| Prompt injection via a crafted PDF | Field validation at storage, untrusted-data fence, system-prompt rule; tools are read-only and session-scoped |
| Cost and abuse | Per-user budgets, login lockout per email and IP, nginx sign-in limit, body caps |
| Network exposure | TLS only (HTTP redirects); Redis and the backend not reachable from outside; X-Forwarded-* trusted only from nginx's fixed IP |
| Container escape impact | Non-root users, `no-new-privileges`, resource limits, no secrets in images |

## Vector index lifecycle

```
database/vector_index/
├── CURRENT                         "20261025T183755Z-9e03"
└── versions/
    ├── 20261025T183018Z/           previous (rollback target)
    └── 20261025T183755Z-9e03/
        ├── chroma.sqlite3 …
        └── manifest.json           embedding_type, embedding_model, embedding_dims,
                                    total_chunks, chunks_per_file, sources_sha256, validation
```

- **Build** (`python -m app.services.vector_index build`, or the admin API) takes an exclusive file
  lock, writes a new version, validates it and writes the manifest last. Only then is `CURRENT`
  replaced (`os.replace`, atomic). Old versions beyond `VECTOR_INDEX_KEEP` are pruned; the active
  one never is.
- **Serve.** Each process checks `CURRENT` at most every 5 s and opens the new version. It uses
  the embedding model recorded in the manifest and refuses a version whose stored vector size
  doesn't match that model, staying on the version it already has.
- **Rollback** (`activate <version>`) is the same pointer switch.

This replaced an earlier design in which every worker rebuilt the shared index in place at startup
whenever the PDFs changed. That raced across workers and processes, and it hid a second problem:
the original index's embedding model (`models/embedding-001`) had been retired, so query vectors
silently fell back to a different model and every vector search failed with a dimension error.

## Failure modes

| Failure | Behavior |
|---------|----------|
| Gemini slow or rate-limited | Each call times out at 60 s and retries with backoff; the turn ends at 120 s with a "took too long" message |
| Intent classifier down | One retry, then the question goes straight to the adviser |
| Embedding API unavailable at serve time | That process keeps its current index; semantic search errors are absorbed by the DB-first search path |
| New index fails validation | Build rejected (422 from the admin API); active version unchanged |
| Redis down | Requests fail (auth, limits and sessions depend on it); `/api/health` stays up for liveness |
| Browser disconnects mid-answer | Agent task cancelled |
| A worker restarts | No user-visible effect: all state is in Redis |
| Certificate near expiry | certbot renews within 30 days of expiry; nginx reloads every 6 h |

## Deployment topology

| | Development | Production (`docker-compose.prod.yml`) |
|-|-------------|-----------------------------------------|
| Public ports | 8443 HTTPS, 8080 → redirect | 443 HTTPS, 80 → redirect + ACME |
| Certificate | Self-signed (`scripts/gen-dev-cert.sh`) | Let's Encrypt via certbot |
| Demo account | Optional (`DEMO_LOGIN_ENABLED`) | Forced off |
| Backend | 127.0.0.1:8000 (Swagger UI for debugging) | same; only nginx reaches it |
| Network | Bridge `172.28.0.0/24`, nginx fixed at `172.28.0.10` | same |

## Observability

- **Logs.** Structured lines without student content (counts and lengths only).
- **Traces.** With LangSmith enabled, `chat_turn` is the root run; the intent chain and the
  LangGraph run (every model and tool call) nest under it. Runs are grouped into threads by
  `session_id`. A global client with an anonymizer redacts emails, IDs and labelled names before
  upload, and the user is a keyed hash. OCR and summary calls record sizes only.
- **Health.** `/api/health` for liveness (used by Docker); `/api/status` (authenticated,
  rate-limited) reports vector index, Gemini and streaming.

## Design decisions

- **Own JWTs instead of passing Azure AD tokens through.** One token format for every sign-in
  method, roles under our control, and revocation independent of Azure AD.
- **HttpOnly cookie instead of a token in `localStorage`.** An XSS bug can still act as the user
  while the page is open, but cannot exfiltrate a reusable credential.
- **Fail open on intent.** The gate saves cost on off-topic questions; the adviser can only use
  read-only academic tools, so answering an off-topic question is cheap to tolerate, while
  refusing every question during an outage is not.
- **Minimize, then redact.** Removing the student's name and ID from the prompt did more than any
  regex could: free-text model reasoning once repeated the name, which redaction cannot catch.
- **Offline, versioned indexes.** Builds are slow and can fail; doing them out of band, validating
  before switching, and keeping old versions turns an outage risk into a routine operation.
- **Tailwind compiled at build time.** Removes the last reason for `'unsafe-inline'` in the CSP.

## Known limitations

- Microsoft sign-in is unit-tested but not yet exercised against a real Azure AD app registration.
- LangSmith tracing is verified by capturing the client's HTTP payloads, not against the service.
- Rate limits count requests, not tokens; one very long conversation can still be expensive.
- Redis is a single instance without replication or backups beyond AOF.
- `package-lock.json` files are git-ignored, so frontend builds are not fully reproducible.
- `/api/status` makes a real Gemini call (rate-limited per user).
