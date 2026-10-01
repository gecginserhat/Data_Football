import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { NotLoaded } from "@/components/analysis/States";
import { WellnessForm } from "@/components/performance/WellnessForm";
import { TaskCards } from "@/components/squad/TaskCards";
import { getMe } from "@/lib/api";
import { selectTenant } from "@/lib/actions";
import { todayIso } from "@/lib/performance";
import { getCards, squadAccess } from "@/lib/squad";

type Search = { error?: string; saved?: string };

export default async function MePage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations();
  const result = await getMe();
  if (result.status !== "ok") return null;
  const { me } = result;
  const activeId = me.active_tenant?.tenant_id;
  const access = await squadAccess();
  const ownLoad = me.active_tenant?.permissions.load_wellness === "own";
  const cards = access.playerId && access.cards ? await getCards(access.playerId) : null;

  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t("pages.me.title")}</h1>

      <section
        aria-labelledby="account"
        className="mb-6 rounded-lg border border-line bg-surface p-5"
      >
        <h2 id="account" className="font-condensed text-lg font-semibold">
          {t("pages.me.account")}
        </h2>
        <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <dt className="text-ink-3">{t("pages.me.email")}</dt>
          <dd data-testid="me-email">{me.email ?? "—"}</dd>
          <dt className="text-ink-3">{t("pages.me.activeClub")}</dt>
          <dd data-testid="me-active-club">{me.active_tenant?.tenant_name ?? t("app.noClub")}</dd>
          <dt className="text-ink-3">{t("pages.me.roles")}</dt>
          <dd data-testid="me-roles">
            {me.active_tenant?.roles.map((role) => t(`roles.${role}`)).join(", ") ?? "—"}
          </dd>
        </dl>
      </section>

      {access.playerId && access.cards ? (
        <section aria-labelledby="cards" className="mb-6">
          <h2 id="cards" className="mb-3 font-condensed text-lg font-semibold">
            {t("cards.title")}
          </h2>
          {cards?.status === "ok" ? (
            <TaskCards cards={cards.data.cards} />
          ) : cards ? (
            <NotLoaded result={cards} />
          ) : null}
        </section>
      ) : null}

      {ownLoad && access.playerId ? (
        <section aria-labelledby="wellness" className="mb-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="wellness" className="font-condensed text-lg font-semibold">
              {t("performance.wellness.ownTitle")}
            </h2>
            <Link
              href={`/performance/players/${access.playerId}`}
              className="text-sm text-pri underline-offset-2 hover:underline"
            >
              {t("performance.ownLoad")}
            </Link>
          </div>
          {search.error ? (
            <p
              role="alert"
              className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg"
            >
              {t("performance.errors.generic", { code: search.error })}
            </p>
          ) : null}
          {search.saved === "wellness" ? (
            <p
              role="status"
              className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos"
            >
              {t("performance.saved.wellness")}
            </p>
          ) : null}
          <WellnessForm
            players={[{ id: access.playerId, name: "" }]}
            today={todayIso()}
            returnTo="me"
          />
        </section>
      ) : null}

      <section aria-labelledby="memberships">
        <h2 id="memberships" className="mb-3 font-condensed text-lg font-semibold">
          {t("pages.me.memberships")}
        </h2>
        {me.memberships.length === 0 ? (
          <EmptyState title={t("app.noClub")} description={t("pages.me.noMemberships")} />
        ) : (
          <>
            {!activeId ? (
              <p className="mb-3 text-sm text-ink-2">{t("pages.me.selectClub")}</p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {me.memberships.map((m) => (
                <li
                  key={m.tenant_id}
                  className="flex items-center justify-between gap-4 rounded-lg border border-line bg-surface p-4"
                >
                  <div>
                    <p className="font-medium">{m.tenant_name}</p>
                    <p className="text-sm text-ink-3">
                      {m.roles.map((role) => t(`roles.${role}`)).join(", ")}
                    </p>
                  </div>
                  {m.tenant_id === activeId ? (
                    <span className="rounded bg-accent px-2 py-1 text-xs font-semibold text-accent-ink">
                      {t("pages.me.active")}
                    </span>
                  ) : (
                    <form action={selectTenant}>
                      <input type="hidden" name="tenantId" value={m.tenant_id} />
                      <button
                        type="submit"
                        className="min-h-11 rounded-md border border-line px-4 text-sm"
                      >
                        {t("pages.me.select")}
                      </button>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
