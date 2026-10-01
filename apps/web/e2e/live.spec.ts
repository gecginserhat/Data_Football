import { devices, expect, test, type Browser, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 5 kabul kriterleri (SPEC §16 akış 2): PWA kurulabilir; uçak modunda 20 kayıt çevrimiçine
 * dönünce sunucuya bir kez gider; iki cihaz aynı maçın kayıtlarını paylaşır. Test, oluşturduğu
 * kayıtları sonunda siler (silme mezar taşı olarak kalır, duran top satırları kalkar).
 */
test.describe.configure({ mode: "serial" });

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({ path: `../../docs/demo/faz5/${name}.png`, fullPage: true });
  }
};

interface ServerTag {
  id: string;
  device_id: string;
  deleted: boolean;
}

async function openSamsunspor(page: Page) {
  await page.goto("/live");
  const fixture = page.getByTestId("live-upcoming").locator('[data-fixture-week="7"]');
  await expect(fixture).toContainText("Samsunspor");
  await fixture.click();
  await expect(page).toHaveURL(/\/live\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("live-tagger")).toBeVisible();
  await expect(page.getByTestId("live-status")).toHaveAttribute("data-session", /[0-9a-f-]{36}/);
}

async function serverTags(page: Page): Promise<ServerTag[]> {
  const session = await page.getByTestId("live-status").getAttribute("data-session");
  const response = await page.request.get(`/api/live/sessions/${session}/tags?since=0`);
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { tags: ServerTag[] }).tags;
}

/** Testin bıraktığı kayıtları sunucudan siler (metrik görünümleri worker'da yenilenir). */
async function cleanup(page: Page, ids: string[]) {
  if (ids.length === 0) return;
  const session = await page.getByTestId("live-status").getAttribute("data-session");
  const response = await page.request.post(`/api/live/sessions/${session}/sync`, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
    data: {
      device_id: "e2e-cleanup",
      changes: ids.map((id) => ({ id, op: "delete", client_ts: new Date().toISOString() })),
    },
  });
  expect(response.ok()).toBe(true);
}

const pending = (page: Page) => page.getByTestId("live-pending");

test("the app is installable as a PWA", async ({ page }) => {
  await signIn(page, "analyst");
  await page.goto("/live");
  const manifest = await page.request.get("/manifest.webmanifest");
  expect(manifest.ok()).toBe(true);
  const body = (await manifest.json()) as { display: string; icons: { sizes: string }[] };
  expect(body.display).toBe("standalone");
  expect(body.icons.map((i) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  await page.evaluate(() => navigator.serviceWorker.ready);
  const cdp = await page.context().newCDPSession(page);
  const { installabilityErrors } = (await cdp.send("Page.getInstallabilityErrors")) as {
    installabilityErrors: { errorId: string }[];
  };
  // Playwright bağlamları gizli pencere sayılır; bu tek hata ortamdan gelir, uygulamadan değil.
  const errors = installabilityErrors.map((e) => e.errorId).filter((id) => id !== "in-incognito");
  expect(errors).toEqual([]);
});

test("airplane mode: 20 tags recorded offline reach the server once", async ({ page, context }) => {
  await signIn(page, "analyst");
  await openSamsunspor(page);
  await page.evaluate(() => navigator.serviceWorker.ready);
  // Hizmet çalışanı maç sayfasını önbelleğe alınca çevrimdışı yenileme mümkün olur.
  await expect
    .poll(() => page.evaluate(async () => Boolean(await caches.match(location.pathname))))
    .toBe(true);
  await expect(pending(page)).toHaveAttribute("data-count", "0");
  await expectNoSeriousA11yViolations(page);
  await shot(page, "live-online");

  await context.setOffline(true);
  await expect(page.getByTestId("live-status")).toContainText("Çevrimdışı");
  // Yarısı dokunarak, yarısı klavye kısayollarıyla.
  const outcomes = page.getByTestId("live-outcomes").getByRole("button");
  for (let i = 0; i < 10; i += 1) await outcomes.nth(i % 8).click();
  for (let i = 0; i < 10; i += 1) {
    await page.keyboard.press(i % 2 ? "f" : "c");
    await page.keyboard.press(String((i % 8) + 1));
  }
  await expect(pending(page)).toHaveAttribute("data-count", "20");
  const created = await page
    .getByTestId("live-tags")
    .locator('[data-pending="1"]')
    .evaluateAll((items) => items.map((i) => i.getAttribute("data-tag-id") ?? ""));
  expect(created).toHaveLength(20);
  await shot(page, "live-offline");

  // Bağlantı yokken sayfa yenilenir: hizmet çalışanı sayfayı, IndexedDB kayıtları getirir.
  await page.reload();
  await expect(page.getByTestId("live-tagger")).toBeVisible();
  await expect(pending(page)).toHaveAttribute("data-count", "20");

  await context.setOffline(false);
  await expect(page.getByTestId("live-status")).toContainText("Çevrimiçi");
  await expect(pending(page)).toHaveAttribute("data-count", "0", { timeout: 30_000 });

  try {
    const tags = (await serverTags(page)).filter((t) => created.includes(t.id));
    expect(tags).toHaveLength(20);
    expect(new Set(tags.map((t) => t.id)).size).toBe(20);
    expect(tags.every((t) => !t.deleted)).toBe(true);
    // Aynı kuyruğun yeniden gönderilmesi kopya üretmez.
    await page.getByRole("button", { name: "Şimdi gönder" }).click();
    await expect(pending(page)).toHaveAttribute("data-count", "0");
    expect((await serverTags(page)).filter((t) => created.includes(t.id))).toHaveLength(20);
  } finally {
    await cleanup(page, created);
  }
});

function contextOptions() {
  const { baseURL, locale } = test.info().project.use;
  return { ...devices["Galaxy Tab S4"], baseURL, locale };
}

async function secondDevice(browser: Browser): Promise<Page> {
  const context = await browser.newContext(contextOptions());
  return context.newPage();
}

test("two devices share tags and deletions", async ({ page, browser }) => {
  await signIn(page, "analyst");
  await openSamsunspor(page);
  const other = await secondDevice(browser);
  await signIn(other, "sp-coach");
  await openSamsunspor(other);

  await page.locator("#live-clock-input").fill("88:17");
  await page.getByRole("button", { name: "Ayarla" }).click();
  await page.keyboard.press("t");
  await page.keyboard.press("h");
  await page.keyboard.press("6");
  const tagId = await page
    .getByTestId("live-tags")
    .locator("li")
    .first()
    .getAttribute("data-tag-id");
  expect(tagId).toBeTruthy();
  try {
    const remote = other.locator(`[data-tag-id="${tagId}"]`);
    await expect(remote).toContainText("88:17", { timeout: 20_000 });
    await expect(remote).toContainText("Uzaklaştırıldı");
    await expect(remote).toContainText("SAM");
    await shot(other, "live-second-device");

    await remote.getByRole("button", { name: "Sil", exact: true }).click();
    await remote.getByRole("button", { name: "Silmeyi onayla" }).click();
    await expect(page.locator(`[data-tag-id="${tagId}"]`)).toHaveCount(0, { timeout: 20_000 });
  } finally {
    await cleanup(page, [tagId ?? ""].filter(Boolean));
    await other.context().close();
  }
});

test("the last tag can be undone within ten seconds", async ({ page }) => {
  await signIn(page, "analyst");
  await openSamsunspor(page);
  await page.keyboard.press("c");
  await page.keyboard.press("2");
  const first = page.getByTestId("live-tags").locator("li").first();
  const tagId = await first.getAttribute("data-tag-id");
  await expect(page.getByTestId("live-undo")).toBeVisible();
  await page.keyboard.press("z");
  await expect(page.locator(`[data-tag-id="${tagId}"]`)).toHaveCount(0);
  // Senkronizasyondan önce geri alındıysa yalnız mezar taşı gider; sonra alındıysa silinir.
  await expect
    .poll(async () => (await serverTags(page)).find((t) => t.id === tagId)?.deleted, {
      timeout: 20_000,
    })
    .toBe(true);
});

const FOULS = "Ceza sahası çevresinde faul kazanın";
const CORNERS = "Korner savunması haftanın öncelikli çalışması";

async function accept(page: Page, title: string) {
  const card = page.getByTestId("recommendation").filter({ hasText: title });
  const status = await card.getAttribute("data-status");
  if (status === "accepted") return;
  if (status === "rejected") {
    if (!(await card.isVisible())) await page.getByText(/Reddedilen öneriler/).click();
    await card.getByRole("button", { name: "Kararı geri al" }).click();
    await expect(card).toHaveAttribute("data-status", "suggested");
  }
  await card.getByRole("button", { name: "Kabul et" }).click();
  await expect(card).toHaveAttribute("data-status", "accepted");
}

test("prep page shows match tags next to accepted recommendations", async ({ page }) => {
  await signIn(page, "sp-coach");
  await openSamsunspor(page);
  const fixtureId = page.url().split("/").pop();
  const ids: string[] = [];
  try {
    for (const keys of [
      ["f", "a", "1"],
      ["c", "h", "6"],
    ]) {
      for (const key of keys) await page.keyboard.press(key);
      ids.push(
        (await page.getByTestId("live-tags").locator("li").first().getAttribute("data-tag-id"))!,
      );
    }
    for (const id of ids) {
      await expect(page.locator(`[data-tag-id="${id}"]`)).toHaveAttribute("data-pending", "0", {
        timeout: 20_000,
      });
    }

    await page.goto(`/prep/${fixtureId}`);
    await accept(page, FOULS);
    await accept(page, CORNERS);
    const panel = page.getByTestId("feedback-panel");
    await expect(panel).toContainText("ilişki gösterimidir, neden-sonuç değildir");
    const attack = panel.locator('[data-area="attack"]');
    await expect(attack).toContainText(FOULS);
    await expect(attack).toContainText("Serbest vuruş");
    await expect(attack).toContainText("Gol");
    const defense = panel.locator('[data-area="defense"]');
    await expect(defense).toContainText(CORNERS);
    await expect(defense).toContainText("Uzaklaştırıldı");
    await expectNoSeriousA11yViolations(page);
    await shot(page, "prep-feedback");
  } finally {
    await page.goto(`/live/${fixtureId}`);
    await expect(page.getByTestId("live-status")).toHaveAttribute("data-session", /[0-9a-f-]{36}/);
    await cleanup(page, ids);
  }
});
