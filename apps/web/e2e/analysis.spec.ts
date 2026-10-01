import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 2 kabul kriterleri: genel bakış, lig ve rakip sayfaları tohum verisiyle doğru sayıları
 * gösterir; az veri ve kaynak rozetleri görünür. Tohum yüklü olmalıdır (`make seed`).
 */
const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({
      path: `../../docs/demo/faz2/${test.info().project.name}-${name}.png`,
      fullPage: true,
    });
  }
};

async function openLastSeasonLeague(page: Page) {
  await page.goto("/league");
  await page.getByRole("link", { name: "Süper Lig · 2025/26" }).click();
  await expect(page.getByRole("link", { name: "Süper Lig · 2025/26" })).toHaveAttribute(
    "aria-current",
    "page",
  );
}

test("league page shows the 2025/26 golden numbers", async ({ page }) => {
  await signIn(page, "analyst");
  await openLastSeasonLeague(page);

  const totals = page.getByTestId("league-totals");
  await expect(totals.locator('[data-total="set_piece_goal_share"] dd')).toHaveText("%20,4");
  await expect(totals.locator('[data-total="set_piece_goals"] dd')).toHaveText("166");
  await expect(totals.locator('[data-total="goals"] dd')).toHaveText("812");

  const table = page.getByRole("table", { name: "Duran top tablosu" });
  const ts = table.locator('tr[data-team="TS"]');
  await expect(ts.locator('td[data-metric="set_piece_goals"]')).toContainText("15");
  await expect(ts.locator('td[data-metric="set_piece_goals"]')).toContainText("(1.)");
  const goz = table.locator('tr[data-team="GÖZ"]');
  await expect(goz.locator('td[data-metric="set_piece_xg"]')).toContainText("15,4");
  await expect(goz.locator('td[data-metric="set_piece_xg"]')).toContainText("(1.)");
  // Varsayılan sıralama duran top golü: ilk satır Trabzonspor.
  await expect(table.locator("tbody tr").first()).toHaveAttribute("data-team", "TS");
  // Başlığa tıklayınca xG'ye göre sıralanır: ilk satır Göztepe.
  await table.getByRole("button", { name: "DT xG" }).click();
  await expect(table.locator("tbody tr").first()).toHaveAttribute("data-team", "GÖZ");

  await expect(page.getByRole("img", { name: "Duran top xG ve gol" })).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "league-2025-26");
});

test("opponent profile shows bars, badges and the club marker", async ({ page }) => {
  await signIn(page, "analyst");
  await openLastSeasonLeague(page);
  await page
    .getByRole("table", { name: "Duran top tablosu" })
    .getByRole("link", { name: /Göztepe/ })
    .click();

  await expect(page.getByRole("heading", { level: 1, name: /Göztepe/ })).toBeVisible();
  const xg = page.locator('[data-metric="set_piece_xg"]').first();
  await expect(xg).toContainText("15,4");
  await expect(xg).toContainText("1./18");
  await expect(page.getByText("Kaynak: tohum").first()).toBeVisible();
  await expect(page.getByText("Dolaylı").first()).toBeVisible();
  await expect(page.getByText("Lig ortalaması").first()).toBeVisible();
  await expect(page.getByText("TS (sizin kulübünüz)").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dizi kaydı yok" })).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await shot(page, "opponent-goztepe");
});

test("overview shows club status, last season rank and upcoming opponents", async ({ page }) => {
  await signIn(page, "sp-coach");
  await expect(page.getByRole("heading", { level: 1, name: "Trabzonspor (demo)" })).toBeVisible();
  await expect(page.getByTestId("club-standing")).toContainText("puan");
  await expect(page.getByRole("list", { name: "Son maçlar (yeniden eskiye)" })).toBeVisible();

  const last = page.getByTestId("last-season");
  await expect(last.locator('[data-metric="set_piece_goals"]')).toContainText("15");
  await expect(last.locator('[data-metric="set_piece_goals"] [data-testid="kpi-rank"]')).toHaveText(
    "1./18",
  );
  await expect(page.locator("[data-fixture-week]").first()).toHaveAttribute(
    "data-fixture-week",
    "7",
  );
  await expectNoSeriousA11yViolations(page);
  await shot(page, "overview");

  // Yaklaşan rakibe geçiş: üst → alt istemci gezintisi.
  await page.locator("[data-fixture-week]").first().click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("Trabzonspor (demo)");
  await expect(page.getByText(/6\. hafta itibarıyla/)).toBeVisible();
});

test("current season marks small samples with the Az veri badge", async ({ page }) => {
  await signIn(page, "analyst");
  await page.goto("/opponents");
  await expect(page.getByRole("link", { name: "Süper Lig · 2026/27" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  // Samsunspor 6 maçta 6 gol attı: duran top payının paydası 8'in altında, maç sayısı yeterli.
  await page
    .getByRole("link", { name: /Samsunspor/ })
    .first()
    .click();
  await expect(page.getByText(/6\. hafta itibarıyla/)).toBeVisible();
  const share = page.locator('[data-metric="set_piece_goal_share"]').first();
  await expect(share.getByText("Az veri")).toBeVisible();
  const goals = page.locator('[data-metric="set_piece_goals"]').first();
  await expect(goals.getByText("Az veri")).toHaveCount(0);
  await expectNoSeriousA11yViolations(page);
  await shot(page, "opponent-low-sample");
});
