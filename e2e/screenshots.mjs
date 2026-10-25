// Regenerates the README screenshots in docs/screenshots/ (1440x900) from a running stack.
//
//   cd e2e && npm install && DEMO_USER_PASSWORD=... npm run screenshots
// API_DOCS_URL defaults to the backend's Swagger UI on loopback (not exposed through nginx).
import { fileURLToPath } from 'node:url';
import { ask, finishedTurns, openBrowser, signIn, waitUntil } from './lib.mjs';

const OUT = fileURLToPath(new URL('../docs/screenshots/', import.meta.url));
const TRANSCRIPT = fileURLToPath(new URL('./fixtures/sample-transcript.pdf', import.meta.url));
const API_DOCS_URL = process.env.API_DOCS_URL || 'http://127.0.0.1:8000/docs';
const QUESTION = 'What are the required courses for the MSIT program, and who teaches each one?';

const { browser, page } = await openBrowser();
const shot = async (name) => {
  await page.screenshot({ path: `${OUT}${name}.png` });
  console.log(`  wrote docs/screenshots/${name}.png`);
};

// 1. Login: the demo form only appears when the backend enables it
await page.goto(process.env.BASE_URL || 'https://localhost:8443', { waitUntil: 'networkidle' });
await page.getByText('Sign in to Demo').waitFor();
await page.waitForTimeout(1200); // entrance animation
await shot('login');

// 2. Chat home with the live status panel
await signIn(page);
await waitUntil(page, () => /ONLINE|READY/.test(document.body.innerText), { what: 'status panel' });
await page.waitForTimeout(800);
await shot('chat-home');

// 3. Agent process mid-run: thoughts and tool calls streaming in
await ask(page, QUESTION);
await waitUntil(page, () => document.querySelectorAll('code').length >= 3 || /Reasoned with/.test(document.body.innerText),
  { what: 'tool calls', interval: 250 });
await page.evaluate(() => document.querySelector('main, [class*="overflow-y-auto"]')?.scrollBy(0, 99999));
await shot('agent-thinking');

// 4. Finished answer, process collapsed
await waitUntil(page, finishedTurns, { what: 'answer' });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const scroller = [...document.querySelectorAll('*')].find((el) => el.scrollHeight > el.clientHeight + 50 && getComputedStyle(el).overflowY === 'auto');
  const question = [...document.querySelectorAll('div')].find((el) => el.childElementCount === 0 && el.textContent.includes('required courses for the MSIT'));
  if (scroller && question) scroller.scrollTop = question.getBoundingClientRect().top + scroller.scrollTop - 120;
});
await page.waitForTimeout(500);
await shot('chat-answer');

// 5. Transcript upload, then a personal degree-progress answer
await page.setInputFiles('input[type="file"]', TRANSCRIPT);
await waitUntil(page, () => document.body.innerText.includes('Transcript processed'), { what: 'transcript', timeout: 120000 });
await ask(page, 'Based on my transcript, what do I still need to finish the MSIT degree?');
await waitUntil(page, () => (document.body.innerText.match(/Reasoned with \d+ tool call/g)?.length ?? 0) >= 2, { what: 'progress answer' });
await page.waitForTimeout(1500);
await page.evaluate(() => {
  const scroller = [...document.querySelectorAll('*')].find((el) => el.scrollHeight > el.clientHeight + 50 && getComputedStyle(el).overflowY === 'auto');
  const marker = [...document.querySelectorAll('strong, p')].find((el) => el.textContent.includes('Transcript processed'));
  if (scroller && marker) scroller.scrollTop = marker.getBoundingClientRect().top + scroller.scrollTop - 140;
});
await page.waitForTimeout(500);
await shot('transcript-progress');

// 6. API docs (Swagger UI)
await page.goto(API_DOCS_URL, { waitUntil: 'networkidle' });
await page.waitForSelector('.opblock', { timeout: 15000 });
await page.waitForTimeout(800);
await shot('api-docs');

await browser.close();
