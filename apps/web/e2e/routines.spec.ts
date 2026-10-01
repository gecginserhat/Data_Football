import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 3 kabul kriterleri: şablondan rutin, klavyeyle düzenleme, aynalama, geri al / yinele,
 * sürümleme, karşılaştırma ve PNG/PDF dışa aktarma. Şablonlar yüklü olmalıdır (`make seed`).
 */
const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz3/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

const label = (page: Page, element: string) =>
  page
    .locator(`[data-testid="routine-board"] [data-element="${element}"]`)
    .getAttribute("aria-label");

test("templates load and become an editable, versioned routine", async ({ page }) => {
  await signIn(page, "analyst");
  await page.goto("/routines?tab=templates");
  const templates = page.getByTestId("template-list").locator("[data-template]");
  await expect(templates).toHaveCount(7);
  await expectNoSeriousA11yViolations(page);
  await shot(page, "templates");

  const first = templates.first();
  const name = (await first.locator("h2").textContent())!.trim();
  await first.getByRole("button", { name: "Kütüphaneye ekle" }).click();
  await expect(page).toHaveURL(/\/routines\/[0-9a-f-]{36}\?created=1$/);
  const routineUrl = page.url().replace(/\?.*$/, "");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
  await expect(page.getByTestId("save-state")).toHaveText("Sürüm 1 kayıtlı.");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "editor");

  // Klavye: oyuncuyu seç ve ok tuşuyla 0,5 m kaydır.
  const player = page.locator('[data-testid="routine-board"] [data-element="p1"]');
  const start = await label(page, "p1");
  await player.focus();
  await page.keyboard.press("ArrowLeft");
  const nudged = await label(page, "p1");
  expect(nudged).not.toBe(start);
  await expect(page.getByTestId("save-state")).toContainText("Kaydedilmemiş değişiklik");

  // Aynala, geri al, yinele.
  await page.getByTestId("mirror").click();
  const mirrored = await label(page, "p1");
  expect(mirrored).not.toBe(nudged);
  await page.getByTestId("undo").click();
  expect(await label(page, "p1")).toBe(nudged);
  await page.getByTestId("redo").click();
  expect(await label(page, "p1")).toBe(mirrored);
  await page.keyboard.press("Control+z");
  expect(await label(page, "p1")).toBe(nudged);
  await page.keyboard.press("Control+Shift+z");
  expect(await label(page, "p1")).toBe(mirrored);

  // Kaydet: yeni sürüm.
  await page.getByLabel("Değişiklik notu").fill("Aynalandı");
  await page.getByTestId("save").click();
  await expect(page.getByText("Sürüm 2 kaydedildi.")).toBeVisible();
  const versions = page.getByTestId("version-list");
  await expect(versions.getByRole("listitem")).toHaveCount(2);
  await expect(versions).toContainText("Aynalandı");
  await shot(page, "saved");

  // Karşılaştırma.
  await page.getByTestId("compare").click();
  await expect(page).toHaveURL(/\/compare\?a=1&b=2$/);
  await expect(page.getByTestId("diff-list")).toContainText("oyuncunun yeri değişti");
  await expect(page.getByTestId("diff-list")).toContainText("Taraf değişti");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "compare");

  // Eski sürüm salt okunur açılır.
  await page.goto(`${routineUrl}?v=1`);
  await expect(page.getByTestId("old-version")).toBeVisible();
  await expect(page.getByTestId("save")).toHaveCount(0);

  // Dışa aktarma.
  await page.goto(routineUrl);
  for (const [format, magic] of [
    ["pdf", "%PDF"],
    ["png", "\u0089PNG"],
  ] as const) {
    const download = page.waitForEvent("download");
    await page.getByTestId(`export-${format}`).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(new RegExp(`-v2\\.${format}$`));
    const bytes = await readFile((await file.path())!);
    expect(bytes.subarray(0, 4).toString("latin1")).toBe(magic);
  }

  // Arşivle: kütüphaneden kalkar, arşiv filtresinde görünür.
  await page.getByTestId("archive").click();
  await expect(page).toHaveURL(/\/routines\?archived=1$/);
  await expect(page.getByTestId("routine-list")).toContainText(name);
});

test("library lists routines with usage and the new-routine form", async ({ page }) => {
  await signIn(page, "sp-coach");
  await page.goto("/routines");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Rutinler");
  await page.getByText("Yeni boş rutin").click();
  const routineName = `Kısa korner ${test.info().project.name} ${Date.now()}`;
  await page.getByLabel("Ad").fill(routineName);
  await page.getByRole("button", { name: "Oluştur" }).click();
  await expect(page).toHaveURL(/\/routines\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(routineName);

  // Boş tahtaya oyuncu ekle: araç P, sahaya tıkla.
  const board = page.getByTestId("routine-board");
  await page
    .getByRole("button", { name: /Oyuncu/ })
    .first()
    .click();
  const box = (await board.boundingBox())!;
  await board.click({ position: { x: box.width * 0.5, y: box.height * 0.3 } });
  await expect(board.locator('[data-element="p1"]')).toHaveCount(1);
  await page.keyboard.press("Control+s");
  await expect(page.getByText("Sürüm 2 kaydedildi.")).toBeVisible();

  await page.goto("/routines");
  const card = page
    .getByTestId("routine-list")
    .getByRole("listitem")
    .filter({ hasText: routineName });
  await expect(card).toContainText("Henüz maçta kullanılmadı");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "library");
});
