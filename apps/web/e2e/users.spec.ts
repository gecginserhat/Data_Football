import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

/**
 * Kullanıcı yönetimi ve denetim kaydı (SPEC §12.1, A-100). Rol değişikliği yalnız `medical`
 * geliştirme kullanıcısına yapılır ve geri alınır; başka E2E testi o kullanıcıyı kullanmaz.
 */

const writer = () =>
  test.skip(
    test.info().project.name !== "desktop",
    "Paylaşılan demo durumunu yalnız bir proje yazar",
  );

function member(page: Page, email: string) {
  return page.locator(`[data-testid="member"][data-email="${email}"]`);
}

async function setRoles(page: Page, email: string, labels: string[]) {
  const card = member(page, email);
  await card.locator("summary").click();
  for (const box of await card.getByRole("checkbox", { name: /./ }).all()) {
    const name = (await box.getAttribute("value")) ?? "";
    if (name) await box.setChecked(false);
  }
  for (const label of labels)
    await card.getByRole("checkbox", { name: new RegExp(`^${label}`) }).check();
  await card.getByTestId("roles-save").click();
  await expect(page.getByRole("status")).toHaveText("Roller kaydedildi.");
}

test("only admins can open user management", async ({ page }) => {
  await signIn(page, "head-coach");
  await page.goto("/admin/users");
  await expect(page.getByText("Bu sayfaya erişiminiz yok")).toBeVisible();
});

test("an admin changes roles, cannot drop the last admin and invites by e-mail", async ({
  page,
}) => {
  writer();
  await signIn(page, "admin");
  await page.goto("/admin/users");
  await expect(
    page.getByRole("heading", { level: 1, name: "Kullanıcılar ve roller" }),
  ).toBeVisible();

  const admin = member(page, "admin@kurgu.local");
  await expect(admin.getByText("Siz")).toBeVisible();

  // Kulübün tek yöneticisi kendi yönetici rolünü bırakamaz.
  await admin.locator("summary").click();
  await admin.getByRole("checkbox", { name: /^Yönetici/ }).uncheck();
  await admin.getByRole("checkbox", { name: "Analist", exact: true }).check();
  await admin.getByTestId("roles-save").click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Kulüpte en az bir yönetici kalmalı",
  );
  await expect(
    member(page, "admin@kurgu.local").getByText("Yönetici", { exact: true }).first(),
  ).toBeVisible();

  // Rol ekle, sonra geri al.
  await setRoles(page, "medical@kurgu.local", ["Sağlık ekibi", "İzleyici"]);
  await expect(member(page, "medical@kurgu.local").getByLabel("Roller")).toContainText("İzleyici");
  await setRoles(page, "medical@kurgu.local", ["Sağlık ekibi"]);
  await expect(member(page, "medical@kurgu.local").getByLabel("Roller")).not.toContainText(
    "İzleyici",
  );

  // Davet gönder, listede gör, geri çek.
  const email = `e2e-davet-${Date.now()}@kurgu.test`;
  const form = page.getByTestId("invite-form");
  await form.getByLabel("E-posta").fill(email);
  await form.getByRole("checkbox", { name: "Analist", exact: true }).check();
  await form.getByTestId("invite-send").click();
  await expect(page.getByRole("status")).toContainText("Davet oluşturuldu");
  const invite = page.locator(`[data-testid="invite"][data-email="${email}"]`);
  await expect(invite).toContainText("Analist");
  await invite.getByTestId("invite-revoke").click();
  await expect(page.getByRole("status")).toHaveText("Davet geri çekildi.");
  await expect(invite).toHaveCount(0);

  // Denetim kaydında görünür ve türe göre süzülür.
  await page.goto("/admin/audit");
  await page.getByLabel("Tür").selectOption({ label: "Davetler" });
  await page.getByRole("button", { name: "Süz" }).click();
  await expect(page).toHaveURL(/action=invite\./);
  const rows = page.getByTestId("audit-row");
  await expect(rows.first()).toHaveAttribute("data-action", "invite.revoked");
  await expect(rows.filter({ hasText: email }).first()).toBeVisible();
  for (const action of await rows.evaluateAll((els) =>
    els.map((e) => e.getAttribute("data-action")),
  )) {
    expect(action).toMatch(/^invite\./);
  }
  await page.goto("/admin/audit?action=member.");
  await expect(page.getByTestId("audit-row").first()).toContainText("Roller değiştirildi");
});
