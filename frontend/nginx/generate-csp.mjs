// Writes the Content-Security-Policy header for nginx from the built index.html.
// Inline <script> blocks are allowed by their sha256 hash, so no 'unsafe-inline' for scripts.
// Usage: node generate-csp.mjs dist/index.html > csp.conf
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const html = readFileSync(process.argv[2], 'utf8');
const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
  .map(([, body]) => `'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`);

const policy = [
  "default-src 'self'",
  `script-src 'self' ${hashes.join(' ')}`.trim(),
  // Tailwind is compiled into a stylesheet at build time, so no inline styles are needed
  // (style properties that React and framer-motion set through the DOM are not affected)
  "style-src 'self' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  // MSAL talks to Azure AD; everything else is same-origin
  "connect-src 'self' https://login.microsoftonline.com",
  "frame-src https://login.microsoftonline.com",
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ');

process.stdout.write(`add_header Content-Security-Policy "${policy}" always;\n`);
