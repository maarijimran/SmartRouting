import { expect, test } from "@playwright/test";
import path from "node:path";

test("register → key → models → upload → ask → route → abstain → consent UI → feedback → analytics", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "correct horse battery";

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password (at least 10 characters)").fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/settings\/keys/);

  // add a (fake-provider) key; it must never be shown again
  await page.getByLabel("Label").fill("e2e");
  await page.getByLabel("API key").fill("sk-or-e2e-test-key-123456");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByText("…3456")).toBeVisible();
  await expect(page.getByText("sk-or-e2e-test-key-123456")).toHaveCount(0);

  await page.goto("/settings/models");
  const pick = async (label, slug) => {
    const value = await page.locator(`select[id="${label}"] option`, { hasText: slug }).getAttribute("value");
    await page.locator(`select[id="${label}"]`).selectOption(value);
  };
  await pick("cheap", "cloud-cheap-demo");
  await pick("strong", "cloud-strong-demo");
  await page.getByRole("button", { name: "Save choice" }).click();
  await expect(page.getByText(/Saved\./)).toBeVisible();

  await page.goto("/chat");
  await page.getByRole("button", { name: "+ New session" }).click();
  await expect(page.getByText("🔒 Local-only")).toBeVisible(); // privacy state always visible
  await page.getByLabel("Upload document (PDF or TXT)").setInputFiles(path.join(__dirname, "fixtures/paper.txt"));
  await expect(page.getByText("paper.txt")).toBeVisible();

  await page.getByLabel("Your question").fill("What accuracy does Alder7 achieve?");
  await page.getByRole("button", { name: /Send/ }).click();
  const summary = page.getByText(/Route: local-demo/);
  await expect(summary).toBeVisible();
  await summary.click(); // expand the route panel
  await expect(page.getByText("Estimated (before sending)")).toBeVisible();
  await expect(page.getByText("Measured (after)")).toBeVisible();

  // Sensitive content with cloud allowed: findings are shown first and the user decides.
  await page.getByLabel("Allow cloud models").check();
  await page.getByLabel("Your question").fill("Summarize the paper. Contact: student42@example.test");
  await page.getByRole("button", { name: /Send/ }).click();
  await expect(page.getByText("Sensitive content found — where should this go?")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Email address" })).toBeVisible();
  await expect(page.getByText("Redacted preview")).toBeVisible();
  await page.getByRole("button", { name: /Answer locally/ }).click();
  await expect(page.getByText("You chose local").first()).toBeAttached();

  // Without a local model, a confidential label leaves only cloud-with-consent: the review
  // dialog offers no local option, and cancelling leaves the turn unsent.
  await page.goto("/admin");
  await page.getByLabel("Enable local-demo").click(); // server-backed toggle: state follows the reload
  await expect(page.getByText("Updated.")).toBeVisible();
  await page.goto("/chat");
  await expect(page.getByText(/Session 1/)).toBeVisible();
  await page.getByLabel("Session label").selectOption("confidential");
  await page.getByLabel("Your question").fill("Summarize the paper please");
  await page.getByRole("button", { name: /Send/ }).click();
  await expect(page.getByText("Sensitive content found — where should this go?")).toBeVisible();
  await expect(page.getByRole("button", { name: /Answer locally/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Send to cloud: cloud-cheap-demo/ })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Waiting for your decision.")).toBeVisible();

  // feedback on the first answer
  await page.getByLabel("Session label").selectOption("public");
  await page.reload();
  await expect(page.getByText("paper.txt")).toBeVisible();
  await page.getByRole("button", { name: "Rate this answer" }).first().click();
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText(/feedback recorded/)).toBeVisible();

  await page.goto("/analytics");
  await expect(page.getByText("requests", { exact: true })).toBeVisible();
});
