// Shared helpers for the browser smoke test and the screenshot script.
import { chromium } from 'playwright';

export const BASE_URL = process.env.BASE_URL || 'https://localhost:8443';
export const DEMO_EMAIL = process.env.DEMO_USER_EMAIL || 'demo@wpi.edu';
export const DEMO_PASSWORD = process.env.DEMO_USER_PASSWORD;

if (!DEMO_PASSWORD) {
  console.error('Set DEMO_USER_PASSWORD (the demo account from .env) and run against a stack with DEMO_LOGIN_ENABLED=true');
  process.exit(2);
}

/** Browser + page that records every console error and CSP violation. */
export async function openBrowser({ width = 1440, height = 900 } = {}) {
  const browser = await chromium.launch();
  // The local stack uses a self-signed certificate
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width, height } });
  const page = await context.newPage();
  const problems = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || /Content Security Policy|Refused to/i.test(m.text())) problems.push(m.text());
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  return { browser, context, page, problems };
}

export async function signIn(page) {
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await page.getByText('Sign in to Demo').waitFor({ timeout: 15000 });
  await page.fill('#demo-email', DEMO_EMAIL);
  await page.fill('#demo-password', DEMO_PASSWORD);
  await page.getByText('Sign in to Demo').click();
  await chatBox(page).waitFor({ timeout: 15000 });
}

export const chatBox = (page) => page.getByPlaceholder(/Ask a question|Agent is thinking/);

export async function ask(page, question) {
  await chatBox(page).fill(question);
  await chatBox(page).press('Enter');
}

/**
 * Poll the page instead of page.waitForFunction: that evaluates a string in the page,
 * which the strict CSP (no 'unsafe-eval') correctly refuses.
 */
export async function waitUntil(page, predicate, { timeout = 150000, interval = 500, what = 'condition' } = {}) {
  const deadline = Date.now() + timeout;
  for (;;) {
    if (await page.evaluate(predicate)) return;
    if (Date.now() > deadline) throw new Error(`Timed out waiting for ${what}`);
    await page.waitForTimeout(interval);
  }
}

/** Number of finished assistant turns ("Reasoned with N tool calls" headers). */
export const finishedTurns = () => document.body.innerText.match(/Reasoned with \d+ tool call/g)?.length ?? 0;
