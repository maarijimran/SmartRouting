import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Automated WCAG 2 A/AA scan of the main pages. Needs the same running stack as flow.spec.js.
const PAGES = ["/login", "/register", "/chat", "/settings/keys", "/settings/models", "/settings/privacy", "/analytics", "/rate", "/admin"];

test("no WCAG A/AA violations on the main pages", async ({ page }) => {
  const results = {};
  for (const path of ["/login", "/register"]) {
    await page.goto(path);
    results[path] = (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations;
  }
  const email = `a11y-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password (at least 10 characters)").fill("correct horse battery");
  await page.getByLabel("Confirm password").fill("correct horse battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/settings\/keys/);
  for (const path of PAGES.slice(2)) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    results[path] = (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations;
  }
  const summary = Object.entries(results)
    .filter(([, v]) => v.length)
    .map(([p, v]) => `${p}: ${v.map((x) => `${x.id} (${x.nodes.length})`).join(", ")}`);
  expect(summary, summary.join("\n")).toEqual([]);
});
