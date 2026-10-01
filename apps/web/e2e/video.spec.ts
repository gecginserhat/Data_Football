import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11yViolations, signIn } from "./helpers";

/**
 * Faz 5 kabul kriteri: video yükleme → HLS → klip → duran topa bağlama → rutin sayfasında klip.
 * Video, ffmpeg `testsrc` deseniyle üretilmiş 10 saniyelik sentetik görüntüdür (A-64). Test
 * oluşturduğu videoyu (klipleriyle), canlı kaydı ve rutini sonunda kaldırır.
 */
const VIDEO = "e2e/fixtures/testsrc-10s.mp4";

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SCREENSHOTS) {
    await page.screenshot({ path: `../../docs/demo/faz5/${name}.png`, fullPage: true });
  }
};

test("uploaded video becomes HLS, a clip links to a tagged set piece and shows on the routine", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const stamp = Date.now().toString(36);
  const routineName = `E2E klip rutini ${stamp}`;
  const clipTitle = `Arka direk golü ${stamp}`;
  let tagId: string | null = null;
  let session: string | null = null;
  let videoUrl: string | null = null;
  let routineUrl: string | null = null;

  await signIn(page, "analyst");
  try {
    // 1. Rutin: kütüphanede boş bir korner rutini.
    await page.goto("/routines");
    await page.getByText("Yeni boş rutin").click();
    await page.locator('form input[name="name"]').fill(routineName);
    await page.getByRole("button", { name: "Oluştur" }).click();
    await expect(page).toHaveURL(/\/routines\/[0-9a-f-]{36}/);
    routineUrl = page.url().replace(/\?.*$/, "");

    // 2. Canlı kayıt: kulübün kornerini bu rutinle gol olarak kaydet.
    await page.goto("/live");
    await page.getByTestId("live-upcoming").locator('[data-fixture-week="7"]').click();
    const status = page.getByTestId("live-status");
    await expect(status).toHaveAttribute("data-session", /[0-9a-f-]{36}/);
    session = await status.getAttribute("data-session");
    await page.locator("#live-clock-input").fill("23:05");
    await page.getByRole("button", { name: "Ayarla" }).click();
    await page.keyboard.press("c");
    await page.keyboard.press("a");
    await page.getByLabel(/^Rutin/).selectOption({ label: routineName });
    await page.getByTestId("live-outcomes").getByRole("button", { name: /Gol/ }).click();
    const tag = page.getByTestId("live-tags").locator("li").filter({ hasText: routineName });
    tagId = await tag.getAttribute("data-tag-id");
    await expect(tag).toHaveAttribute("data-pending", "0", { timeout: 20_000 });

    // 3. Video yükle ve HLS'ye dönüşmesini bekle.
    await page.goto("/video");
    await expectNoSeriousA11yViolations(page);
    const upload = page.getByTestId("video-upload");
    await upload.locator('input[type="file"]').setInputFiles(VIDEO);
    await upload.getByLabel("Başlık").fill(`SAM–TS geniş açı ${stamp}`);
    await upload.getByLabel("Maç").selectOption({ label: "7. hafta · SAM–TS" });
    await upload.getByRole("button", { name: "Yüklemeyi başlat" }).click();
    await expect(page).toHaveURL(/\/video\/[0-9a-f-]{36}$/, { timeout: 60_000 });
    videoUrl = page.url();
    // Playwright'ın Chromium'unda H.264/AAC çözücü yok; HLS teslimi (oynatma listesi ve parça)
    // her tarayıcıda, oynatma ise çözücü varsa doğrulanır.
    const h264 = await page.evaluate(() =>
      MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"'),
    );
    const segment = page.waitForResponse((r) => /seg_\d+\.ts/.test(r.url()), { timeout: 120_000 });
    await expect(page.getByTestId("video-player")).toHaveAttribute("data-manifest", "true", {
      timeout: 120_000,
    });
    expect((await segment).status()).toBe(200);
    if (h264) {
      await expect(page.getByTestId("video-player")).toHaveAttribute("data-ready", "true");
    }
    await expectNoSeriousA11yViolations(page);

    // 4. Klip kes ve duran topa bağla.
    const form = page.getByTestId("clip-form");
    await form.getByLabel("Başlangıç (sn)").fill("1");
    await form.getByLabel("Bitiş (sn)").fill("6.5");
    await form.getByLabel("Klip başlığı").fill(clipTitle);
    const option = form.getByLabel("Duran top").locator("option").filter({ hasText: routineName });
    await form.getByLabel("Duran top").selectOption((await option.getAttribute("value"))!);
    await form.getByRole("button", { name: "Klibi kaydet" }).click();
    const clip = page.getByTestId("clips").locator("li").filter({ hasText: clipTitle });
    await expect(clip).toContainText("00:01–00:06");
    await expect(clip.getByTestId("clip-set-piece")).toContainText(routineName);
    if (h264) {
      await clip.getByRole("button", { name: "Oynat" }).click();
      await expect
        .poll(() =>
          page.getByTestId("video-player").evaluate((v: HTMLVideoElement) => v.currentTime),
        )
        .toBeGreaterThanOrEqual(1);
    }
    await shot(page, "video-clip");

    // 5. Rutin sayfasında klip görünür ve videoya götürür.
    await page.goto(routineUrl);
    const routineClips = page.getByTestId("routine-clips");
    await expect(routineClips).toContainText(clipTitle);
    await expect(routineClips).toContainText("Gol");
    await shot(page, "routine-clips");
    await routineClips.getByRole("link", { name: new RegExp(clipTitle) }).click();
    await expect(page).toHaveURL(/\/video\/[0-9a-f-]{36}\?clip=/);
    await expect(page.getByTestId("video-player")).toHaveAttribute("data-manifest", "true");
  } finally {
    if (videoUrl) {
      await page.goto(videoUrl);
      await page.getByRole("button", { name: "Videoyu sil" }).click();
      await page.getByRole("button", { name: /Silmeyi onayla/ }).click();
      await expect(page).toHaveURL(/\/video$/);
    }
    if (tagId && session) {
      await page.request.post(`/api/live/sessions/${session}/sync`, {
        headers: { "Idempotency-Key": crypto.randomUUID() },
        data: {
          device_id: "e2e-cleanup",
          changes: [{ id: tagId, op: "delete", client_ts: new Date().toISOString() }],
        },
      });
    }
    if (routineUrl) {
      await page.goto(routineUrl);
      await page.getByTestId("archive").click();
    }
  }
});
