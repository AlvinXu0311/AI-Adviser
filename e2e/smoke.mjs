// Browser smoke test against a running stack (default https://localhost:8443).
// Checks what unit tests can't: the real CSP, the HttpOnly session cookie, SSE through nginx,
// transcript upload, and server-side logout. Exits non-zero on the first failed check.
//
//   cd e2e && npm install && DEMO_USER_PASSWORD=... npm run smoke
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { BASE_URL, ask, finishedTurns, openBrowser, signIn, waitUntil } from './lib.mjs';

const TRANSCRIPT = fileURLToPath(new URL('./fixtures/sample-transcript.pdf', import.meta.url));
// The session cookie is scoped to Path=/api, so cookie lookups use an /api URL
const results = [];
const check = (name, fn) => results.push([name, fn]);

const { browser, context, page, problems } = await openBrowser();

check('login page renders under the CSP', async () => {
  await signIn(page);
});

check('session token is not readable by page scripts', async () => {
  const cookies = await context.cookies(`${BASE_URL}/api/`);
  const session = cookies.find((c) => c.name === 'adviser_session');
  assert.ok(session, 'adviser_session cookie set');
  assert.equal(session.httpOnly, true);
  assert.equal(session.secure, true);
  assert.equal(session.sameSite, 'Strict');
  assert.ok(!(await page.evaluate(() => document.cookie)).includes('adviser_session'));
  assert.ok(!/token/i.test((await page.evaluate(() => localStorage.getItem('wpi_adviser_auth'))) || ''));
});

check('chat streams an answer with tool calls', async () => {
  await ask(page, 'What are the core courses for the MSIT program?');
  await waitUntil(page, finishedTurns, { what: 'first answer' });
  const text = await page.evaluate(() => document.body.innerText);
  assert.match(text, /MIS \d{3}/, 'answer mentions MIS courses');
});

check('transcript upload feeds degree progress', async () => {
  await page.setInputFiles('input[type="file"]', TRANSCRIPT);
  await waitUntil(page, () => document.body.innerText.includes('Transcript processed'), { what: 'transcript', timeout: 120000 });
  await ask(page, 'Based on my transcript, how close am I to finishing the MSIT degree?');
  await waitUntil(page, () => (document.body.innerText.match(/Reasoned with \d+ tool call/g)?.length ?? 0) >= 2,
    { what: 'progress answer' });
  // Only the model's answer (after the question); the upload notice itself shows the name to the user
  const answer = await page.evaluate(() => document.body.innerText.split('how close am I to finishing').pop());
  assert.match(answer, /MIS 5\d\d/, 'progress answer uses the uploaded courses');
  assert.ok(!answer.includes('Sample Student'), 'the model was not given the student name');
});

check('logout revokes the session server-side', async () => {
  const before = (await context.cookies(`${BASE_URL}/api/`)).find((c) => c.name === 'adviser_session');
  await page.locator('button[title="Sign out"]').click();
  await page.getByText('Sign in to Demo').waitFor({ timeout: 15000 });
  // Replay the old cookie from a fresh context: the backend must refuse it
  const replay = await browser.newContext({ ignoreHTTPSErrors: true });
  await replay.addCookies([before]);
  const res = await replay.request.get(`${BASE_URL}/api/auth/me`);
  assert.equal(res.status(), 401);
  await replay.close();
});

check('no console errors or CSP violations', async () => {
  assert.deepEqual(problems, []);
});

let failed = 0;
for (const [name, fn] of results) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`  ✗ ${name}\n      ${err.message.split('\n')[0]}`);
    break; // later checks depend on earlier ones
  }
}
await browser.close();
console.log(failed ? '\nSMOKE FAILED' : `\n${results.length} checks passed`);
process.exit(failed ? 1 : 0);
