import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 4 kabul kriterleri: TS (demo kulübü) için 2026/27 7. hafta Samsunspor deplasmanında öneriler
 * kanıt ve güvenle görünür; kabul ve gerekçeli red kaydedilir; MD planı ilerler; kurallar denenir.
 * Demo kiracısının durumu çalıştırmalar arasında kalır; test her adımda başlangıç durumuna döner.
 * Karar ve kural yazan testler paylaşılan durumu değiştirdiği için yalnız masaüstü projesinde
 * çalışır; tablet projesi aynı ekranları okur.
 */
const FOULS = "Ceza sahası çevresinde faul kazanın";
const CORNERS = "Korner savunması haftanın öncelikli çalışması";

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz4/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

const card = (page: Page, title: string) =>
  page.getByTestId("recommendation").filter({ hasText: title });

async function resetDecision(page: Page, title: string) {
  const c = card(page, title);
  const status = await c.getAttribute("data-status");
  if (status === "rejected" && !(await c.isVisible())) {
    await page.getByText(/Reddedilen öneriler/).click();
  }
  if (status !== "suggested") {
    await c.getByRole("button", { name: "Kararı geri al" }).click();
    await expect(card(page, title)).toHaveAttribute("data-status", "suggested");
  }
}

const writer = () =>
  test.skip(
    test.info().project.name !== "desktop",
    "Paylaşılan demo durumunu yalnız bir proje yazar",
  );

async function openSamsunspor(page: Page) {
  await page.goto("/prep");
  const fixture = page.getByTestId("prep-fixtures").locator('[data-fixture-week="7"]');
  await expect(fixture).toContainText("Samsunspor");
  await expect(fixture).toContainText(CORNERS);
  await fixture.click();
  await expect(page).toHaveURL(/\/prep\/[0-9a-f-]{36}$/);
}

test("week 7 at Samsunspor shows evidence-backed recommendations and a weekly plan", async ({
  page,
}) => {
  writer();
  await signIn(page, "sp-coach");
  await expect(page.getByTestId("threats").first()).toContainText(CORNERS);
  await page.goto("/prep");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "list");

  await openSamsunspor(page);
  // Önceki çalıştırmanın kararlarını sıfırla.
  await resetDecision(page, FOULS);
  await resetDecision(page, CORNERS);

  const fouls = card(page, FOULS);
  const corners = card(page, CORNERS);
  await expect(fouls).toBeVisible();
  await expect(corners).toBeVisible();
  await expect(corners).toContainText("Savunma");
  await expect(corners).toContainText("Güven: yüksek");
  await expect(fouls).toContainText("4.");
  await corners.getByText(/Kanıt/).click();
  await expect(corners.getByRole("table")).toContainText("2./");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "recommendations");

  // Kabul: plana MD-4 maddesi olarak girer.
  await corners.getByRole("button", { name: "Kabul et" }).click();
  await expect(card(page, CORNERS)).toHaveAttribute("data-status", "accepted");
  await expect(page.locator('[data-md="MD-4"]')).toContainText(CORNERS);

  // Gerekçesiz red olmaz; gerekçeyle reddedilir.
  await card(page, FOULS).getByText("Reddet", { exact: true }).click();
  await card(page, FOULS).getByLabel("Neden reddediyorsunuz?").fill("Hakem az faul çalıyor");
  await card(page, FOULS).getByRole("button", { name: "Gerekçeyle reddet" }).click();
  await expect(page.getByText(/Reddedilen öneriler \(1\)/)).toBeVisible();
  await page.getByText(/Reddedilen öneriler/).click();
  await expect(card(page, FOULS)).toContainText("Hakem az faul çalıyor");

  // Plan: madde ekle, sorumlu ata, tamamla, ilerleme artar, sonra kaldır.
  const leftovers = page.getByTestId("plan-item").filter({ hasText: "E2E kısa korner provası" });
  while ((await leftovers.count()) > 0) {
    const before = await leftovers.count();
    await leftovers
      .first()
      .getByRole("button", { name: /maddesini kaldır/ })
      .click();
    await expect(leftovers).toHaveCount(before - 1);
  }
  await page.getByText("Madde ekle").click();
  await page.locator("select[name=mdCode]").selectOption("MD-2");
  await page.getByLabel("Başlık").fill("E2E kısa korner provası");
  await page.getByRole("button", { name: "Ekle", exact: true }).click();
  const item = page.getByTestId("plan-item").filter({ hasText: "E2E kısa korner provası" });
  await expect(item).toHaveAttribute("data-status", "todo");
  const progress = await page.getByTestId("plan-progress").textContent();
  const select = item.getByLabel("Sorumlu");
  const options = await select.locator("option").all();
  expect(options.length).toBeGreaterThan(1);
  await select.selectOption({ index: 1 });
  await item.getByRole("button", { name: "Ata" }).click();
  await item.getByRole("button", { name: /tamamlandı olarak işaretle/ }).click();
  await expect(
    page.getByTestId("plan-item").filter({ hasText: "E2E kısa korner provası" }),
  ).toHaveAttribute("data-status", "done");
  await expect(page.getByTestId("plan-progress")).not.toHaveText(progress!);
  await expectNoSeriousA11yViolations(page);
  await shot(page, "plan");
  await page
    .getByTestId("plan-item")
    .filter({ hasText: "E2E kısa korner provası" })
    .getByRole("button", { name: /maddesini kaldır/ })
    .click();
  await expect(
    page.getByTestId("plan-item").filter({ hasText: "E2E kısa korner provası" }),
  ).toHaveCount(0);

  // Kararlar geri alınır; bağlı yapılmamış plan maddesi kalkar.
  await resetDecision(page, FOULS);
  await resetDecision(page, CORNERS);
  await expect(page.locator('[data-md="MD-4"]')).not.toContainText(CORNERS);
});

test("viewer reads recommendations but cannot decide", async ({ page }) => {
  await signIn(page, "viewer");
  await openSamsunspor(page);
  await expect(card(page, CORNERS)).toBeVisible();
  await expect(page.getByRole("button", { name: "Kabul et" })).toHaveCount(0);
  await expect(page.getByTestId("matchup")).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "viewer");
});

test("head coach tries a draft rule set and publishes a version", async ({ page }) => {
  writer();
  await signIn(page, "head-coach");
  await page.goto("/admin");
  await page.getByRole("link", { name: /Öneri kuralları/ }).click();
  await expect(page).toHaveURL(/\/admin\/rules$/);
  const editor = page.getByTestId("rule-editor");
  await expect(editor.locator("[data-rule]")).toHaveCount(25);
  await expectNoSeriousA11yViolations(page);

  // Taslak: korner kuralını kapat ve dene; kaydedilmez.
  const cornerRule = editor.locator('[data-rule="DEF_CORNER_PRIORITY"]');
  await cornerRule.getByRole("checkbox").uncheck();
  await page.getByTestId("dry-run").click();
  const results = page.getByTestId("dry-run-results");
  await expect(results.locator('[data-rule="DEF_CORNER_PRIORITY"]')).toHaveAttribute(
    "data-status",
    "disabled",
  );
  await expect(results.locator('[data-rule="ATK_WIN_FOULS"]')).toHaveAttribute(
    "data-status",
    "fired",
  );
  await shot(page, "rules-dry-run");

  // Yayımla: öncelik değişikliği yeni sürüm açar; sonra eski değer geri yayımlanır.
  await cornerRule.getByRole("checkbox").check();
  const priority = cornerRule.getByLabel("Öncelik", { exact: true });
  const original = await priority.inputValue();
  await priority.fill(original === "1" ? "2" : "1");
  await page.getByLabel("Değişiklik notu").fill("E2E öncelik denemesi");
  await page.getByTestId("publish-rules").click();
  await expect(page.getByText(/Sürüm \d+ yayımlandı/)).toBeVisible();
  await expect(page.getByTestId("rule-versions")).toContainText("E2E öncelik denemesi");
  await page
    .locator('[data-rule="DEF_CORNER_PRIORITY"]')
    .getByLabel("Öncelik", { exact: true })
    .fill(original);
  await page.getByLabel("Değişiklik notu").fill("E2E geri alma");
  await page.getByTestId("publish-rules").click();
  await expect(page.getByTestId("rule-versions")).toContainText("E2E geri alma");
  await shot(page, "rules");
});
