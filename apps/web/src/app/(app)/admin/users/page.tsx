import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { getMe } from "@/lib/api";
import { createInvite, removeMember, revokeInvite, saveRoles } from "@/lib/user-actions";
import { listInvites, listMembers, ROLES, type Role } from "@/lib/users";

type Search = { error?: string; saved?: string };

const MFA_ROLES: ReadonlySet<Role> = new Set(["admin", "medical", "performance"]);

/** Rol onay kutuları; en az biri seçilmelidir (sunucu da denetler). */
async function RolePicker({ selected, idPrefix }: { selected: readonly Role[]; idPrefix: string }) {
  const t = await getTranslations();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{t("users.roles")}</legend>
      <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
        {ROLES.map((role) => (
          <label key={role} className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="roles"
              value={role}
              defaultChecked={selected.includes(role)}
              id={`${idPrefix}-${role}`}
              className="size-5 accent-[var(--pri)]"
            />
            {t(`roles.${role}`)}
            {MFA_ROLES.has(role) ? (
              <span className="rounded border border-line px-1.5 text-[11px] text-ink-2">
                {t("users.mfa")}
              </span>
            ) : null}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Kulüp üyeleri, roller ve davetler (SPEC §12.1, A-100). Yalnız yönetici. */
export default async function UsersPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations();
  const format = await getFormatter();
  const [members, invites, me] = await Promise.all([listMembers(), listInvites(), getMe()]);
  const crumb = (
    <nav aria-label={t("users.breadcrumb")} className="mb-2 text-xs text-ink-3">
      <Link href="/admin" className="underline-offset-2 hover:underline">
        {t("users.admin")}
      </Link>
    </nav>
  );
  if (members.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("users.title")}</PageTitle>
        <NotLoaded result={members} />
      </>
    );
  }
  const myId = me.status === "ok" ? me.me.user_id : null;
  const when = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const message = search.error
    ? t.has(`users.errors.${search.error}`)
      ? t(`users.errors.${search.error}`)
      : t("users.errors.generic", { code: search.error })
    : null;

  return (
    <>
      {crumb}
      <PageTitle sub={t("users.subtitle")}>{t("users.title")}</PageTitle>
      {message ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {message}
        </p>
      ) : null}
      {search.saved && t.has(`users.saved.${search.saved}`) ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t(`users.saved.${search.saved}`)}
        </p>
      ) : null}

      <Section id="members" title={t("users.members", { count: members.data.length })}>
        <ul className="flex flex-col gap-3" data-testid="members">
          {members.data.map((m) => {
            const label = m.name ?? m.email ?? t("users.unnamed");
            return (
              <li
                key={m.user_id}
                className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
                data-testid="member"
                data-email={m.email ?? ""}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {label}
                      {m.user_id === myId ? (
                        <span className="ml-2 rounded border border-accent px-1.5 text-xs">
                          {t("users.you")}
                        </span>
                      ) : null}
                    </p>
                    {m.name && m.email ? <p className="text-sm text-ink-2">{m.email}</p> : null}
                  </div>
                  <p className="text-xs text-ink-3">
                    {m.last_seen_at
                      ? t("users.lastSeen", { date: when(m.last_seen_at) })
                      : t("users.neverSeen")}
                  </p>
                </div>
                <p className="flex flex-wrap gap-1 text-xs" aria-label={t("users.currentRoles")}>
                  {m.roles.map((r) => (
                    <span key={r} className="rounded border border-line px-2 py-0.5">
                      {t(`roles.${r}`)}
                    </span>
                  ))}
                  {m.squad_player_name ? (
                    <span className="rounded border border-line px-2 py-0.5 text-ink-2">
                      {t("users.linkedPlayer", { name: m.squad_player_name })}
                    </span>
                  ) : null}
                </p>
                <details className="group">
                  <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm font-medium text-pri underline-offset-2 hover:underline">
                    {t("users.edit", { name: label })}
                  </summary>
                  <form action={saveRoles} className="mt-2 flex flex-col gap-3">
                    <input type="hidden" name="userId" value={m.user_id} />
                    <RolePicker selected={m.roles} idPrefix={`m-${m.user_id}`} />
                    <div className="flex flex-wrap gap-2">
                      <PendingButton
                        className={btnPrimary}
                        pendingLabel={t("users.pending")}
                        testId="roles-save"
                      >
                        {t("users.saveRoles")}
                      </PendingButton>
                    </div>
                  </form>
                  <form
                    action={removeMember}
                    className="mt-4 flex flex-col gap-2 border-t border-line pt-3"
                  >
                    <input type="hidden" name="userId" value={m.user_id} />
                    <p className="text-sm text-ink-2">{t("users.removeNote")}</p>
                    <label className="flex min-h-11 items-center gap-2 text-sm">
                      <input type="checkbox" name="confirm" required className="size-5" />
                      {t("users.removeConfirm")}
                    </label>
                    <div>
                      <PendingButton
                        className={`${btn} border-neg text-neg`}
                        pendingLabel={t("users.pending")}
                        testId="member-remove"
                      >
                        {t("users.remove", { name: label })}
                      </PendingButton>
                    </div>
                  </form>
                </details>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section id="invite" title={t("users.inviteTitle")}>
        <form
          action={createInvite}
          className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
          data-testid="invite-form"
        >
          <p className="max-w-prose text-sm text-ink-2">{t("users.inviteNote")}</p>
          <label className="flex max-w-md flex-col gap-1 text-sm">
            {t("users.email")}
            <input
              type="email"
              name="email"
              required
              maxLength={254}
              autoComplete="off"
              className={inputCls}
            />
          </label>
          <RolePicker selected={[]} idPrefix="invite" />
          <div>
            <PendingButton
              className={btnPrimary}
              pendingLabel={t("users.pending")}
              testId="invite-send"
            >
              {t("users.inviteSend")}
            </PendingButton>
          </div>
        </form>
      </Section>

      <Section id="invites" title={t("users.invitesTitle")}>
        {invites.status !== "ok" ? (
          <NotLoaded result={invites} />
        ) : invites.data.length === 0 ? (
          <EmptyState title={t("users.invitesEmptyTitle")} description={t("users.invitesEmpty")} />
        ) : (
          <ul className="flex flex-col gap-2" data-testid="invites">
            {invites.data.map((i) => (
              <li
                key={i.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-4"
                data-testid="invite"
                data-email={i.email}
              >
                <div className="flex flex-col gap-1">
                  <p className="font-medium">{i.email}</p>
                  <p className="text-sm text-ink-2">
                    {i.roles.map((r) => t(`roles.${r}`)).join(", ")}
                  </p>
                  <p className="text-xs text-ink-3">
                    {t("users.inviteMeta", {
                      by: i.invited_by_name ?? t("users.unnamed"),
                      date: when(i.created_at),
                      expires: when(i.expires_at),
                    })}
                  </p>
                </div>
                <form action={revokeInvite}>
                  <input type="hidden" name="inviteId" value={i.id} />
                  <PendingButton
                    className={btn}
                    pendingLabel={t("users.pending")}
                    testId="invite-revoke"
                  >
                    {t("users.revoke", { email: i.email })}
                  </PendingButton>
                </form>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <p className="text-sm text-ink-2">
        <Link href="/admin/audit" className="text-pri underline-offset-2 hover:underline">
          {t("audit.link")}
        </Link>
      </p>
    </>
  );
}
