import { expect, test } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 1.9 kabul kriteri: CSV yükle → hatayı gör → eşleştirmeyi düzelt → işle.
 * Tohum verisi yüklü olmalıdır (`make seed`); takım adları tohumdaki Süper Lig takımlarıdır.
 */
/** Sunucu eylemli formlar sayfa hidrate olduktan sonra gönderilir. */
const settled = (page: import("@playwright/test").Page) => page.waitForLoadState("networkidle");

const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz1/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

test("admin uploads a CSV, sees the errors, fixes the mapping and commits", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/admin");
  await page.getByRole("link", { name: /CSV\/Excel içe aktarım/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "İçe aktarım" })).toBeVisible();
  await settled(page);
  await expectNoSeriousA11yViolations(page);

  // Takım sütunu tanınmayan başlıkla, bir takım adı da yazım farkıyla gelir.
  const csv = ["Kulup Adi;Atilan Gol;set_piece_goals", "Trabzonspor;50;13", "Goztepe SK;40;9"].join(
    "\n",
  );
  await page
    .getByRole("combobox", { name: "Sezon" })
    .selectOption({ label: "Süper Lig · 2025/26" });
  await page.getByLabel(/^Dosya/).setInputFiles({
    name: "takim-istatistikleri.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });
  await page.getByRole("button", { name: "Yükle ve doğrula" }).click();

  await expect(page).toHaveURL(/\/admin\/imports\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("import-status")).toHaveText("Karantinada");
  const issues = page.getByTestId("issues");
  await expect(issues).toContainText("zorunlu sütun yok: team");
  await expect(page.getByRole("button", { name: "Veriyi işle" })).toBeDisabled();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "import-quarantined");
  await settled(page);

  await page.getByLabel("Şablon alanı: Kulup Adi").selectOption("team");
  await page.getByLabel("Şablon alanı: Atilan Gol").selectOption("goals");
  await page.getByRole("button", { name: "Eşleştirmeyi kaydet ve yeniden doğrula" }).click();

  await expect(page.getByTestId("import-status")).toHaveText("Onay bekliyor");
  const teams = page.getByTestId("teams");
  await expect(teams).toContainText("Onay bekliyor");
  await settled(page);
  await page.getByLabel("Takım: Goztepe SK").selectOption({ label: "GÖZ · Göztepe" });
  await shot(page, "import-team-confirmation");
  await page.getByRole("button", { name: "Eşleştirmeyi kaydet ve yeniden doğrula" }).click();

  await expect(page.getByTestId("import-status")).toHaveText("İşlenmeye hazır");
  await expect(page.getByText("Sorun bulunmadı.")).toBeVisible();
  await settled(page);
  await page.getByRole("button", { name: "Veriyi işle" }).click();

  await expect(page.getByTestId("import-status")).toHaveText("İşlendi");
  const result = page.getByTestId("result");
  await expect(result).toContainText("takım");
  await expect(result).toContainText("4");
  await expect(page.getByLabel("Şablon alanı: Kulup Adi")).toBeDisabled();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "import-committed");

  await page.getByRole("link", { name: /İçe aktarımlara dön/ }).click();
  await expect(page.getByRole("link", { name: "takim-istatistikleri.csv" }).first()).toBeVisible();
  await shot(page, "imports-list");
});

test("imports are closed to non-admin roles", async ({ page }) => {
  await signIn(page, "analyst");
  await page.goto("/admin/imports");
  await expect(page.getByRole("heading", { name: "Bu sayfaya erişiminiz yok" })).toBeVisible();
});

test("methodology credits StatsBomb Open Data", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/methodology");
  await expect(page.getByRole("heading", { name: "StatsBomb Open Data" })).toBeVisible();
  await expect(page.getByRole("link", { name: /github\.com\/statsbomb\/open-data/ })).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "methodology");
});
