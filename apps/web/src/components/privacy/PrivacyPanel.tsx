import { DemoBadge } from "@kurgu/ui";
import { getFormatter, getTranslations } from "next-intl/server";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import type { ConsentStatus, ConsentText, PrivacyRequest } from "@/lib/privacy";
import { giveConsent, requestErasure, withdrawConsent } from "@/lib/privacy-actions";

/**
 * Oyuncunun iyi oluş rızası, veri kopyası ve silme talebi (KVKK, ADR-0019, A-92). Oyuncu kendi
 * sayfasında, performans ve sağlık ekibi oyuncu sayfasında görür.
 */
export async function PrivacyPanel({
  status,
  text,
  requests,
  returnTo,
  error,
  saved,
}: {
  status: ConsentStatus;
  text: ConsentText;
  requests: PrivacyRequest[];
  returnTo: "me" | "player";
  error?: string;
  saved?: string;
}) {
  const t = await getTranslations("privacy");
  const format = await getFormatter();
  const active = status.active;
  const canChange = status.can_give_self || status.can_record_paper;
  const open = requests.find(
    (r) => r.status === "open" && r.squad_player_id === status.squad_player_id,
  );
  const when = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const hidden = (
    <>
      <input type="hidden" name="playerId" value={status.squad_player_id} />
      <input type="hidden" name="returnTo" value={returnTo} />
    </>
  );

  return (
    <div className="flex flex-col gap-4" data-testid="privacy-panel">
      {error ? (
        <p role="alert" className="rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t.has(`errors.${error}`) ? t(`errors.${error}`) : t("errors.generic", { code: error })}
        </p>
      ) : null}
      {saved && t.has(`saved.${saved}`) ? (
        <p role="status" className="rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t(`saved.${saved}`)}
        </p>
      ) : null}

      <div
        className="rounded-lg border border-line bg-surface p-4"
        data-testid="consent-status"
        data-state={active ? "active" : "none"}
      >
        <p className="font-medium">
          {active ? t("consent.active") : t("consent.none")}
          {active?.is_demo ? (
            <span className="ml-2 align-middle">
              <DemoBadge label={t("demo")} />
            </span>
          ) : null}
        </p>
        <p className="mt-1 text-sm text-ink-2">
          {active
            ? t("consent.activeDetail", {
                method: t(`consent.method.${active.method}`),
                date: when(active.given_at),
                version: active.text_version,
              })
            : t("consent.noneDetail")}
        </p>
        {active?.reference ? (
          <p className="mt-1 text-sm text-ink-2">
            {t("consent.reference")}: {active.reference}
          </p>
        ) : null}

        <details className="mt-3 text-sm">
          <summary className="min-h-11 cursor-pointer py-2 text-pri">
            {t("consent.readText", { version: text.version })}
          </summary>
          <p className="mt-2 max-w-prose text-ink-2" data-testid="consent-text">
            {text.text}
          </p>
        </details>

        {!active && status.can_give_self ? (
          <form action={giveConsent} className="mt-3">
            {hidden}
            <input type="hidden" name="method" value="self" />
            <input type="hidden" name="textVersion" value={text.version} />
            <PendingButton className={btnPrimary} pendingLabel={t("pending")} testId="consent-give">
              {t("consent.give")}
            </PendingButton>
          </form>
        ) : null}
        {!active && status.can_record_paper ? (
          <form action={giveConsent} className="mt-3 flex flex-wrap items-end gap-2">
            {hidden}
            <input type="hidden" name="method" value="paper" />
            <input type="hidden" name="textVersion" value={text.version} />
            <label className="flex flex-col gap-1 text-sm">
              {t("consent.reference")}
              <input
                name="reference"
                required
                maxLength={200}
                className={inputCls}
                data-testid="consent-reference"
                placeholder={t("consent.referencePlaceholder")}
              />
            </label>
            <PendingButton
              className={btnPrimary}
              pendingLabel={t("pending")}
              testId="consent-paper"
            >
              {t("consent.recordPaper")}
            </PendingButton>
          </form>
        ) : null}
        {active && canChange ? (
          <form action={withdrawConsent} className="mt-3">
            {hidden}
            <PendingButton className={btn} pendingLabel={t("pending")} testId="consent-withdraw">
              {t("consent.withdraw")}
            </PendingButton>
            <p className="mt-1 text-xs text-ink-3">{t("consent.withdrawNote")}</p>
          </form>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
        <h3 className="font-medium">{t("rights.title")}</h3>
        <p className="text-sm text-ink-2">{t("rights.description")}</p>
        <a
          href={`/api/privacy/export/${status.squad_player_id}`}
          className={`${btn} self-start`}
          data-testid="export-link"
          download
        >
          {t("rights.export")}
        </a>
        {open ? (
          <p className="text-sm" data-testid="erasure-open">
            {t("rights.erasureOpen", { date: when(open.created_at) })}
          </p>
        ) : (
          <form action={requestErasure} className="flex flex-col gap-2" data-testid="erasure-form">
            {hidden}
            <label className="flex flex-col gap-1 text-sm">
              {t("rights.reason")}
              <textarea name="reason" maxLength={500} rows={2} className={`${inputCls} py-2`} />
            </label>
            <PendingButton
              className={`${btn} self-start`}
              pendingLabel={t("pending")}
              testId="erasure-submit"
            >
              {t("rights.erasure")}
            </PendingButton>
            <p className="text-xs text-ink-3">{t("rights.erasureNote")}</p>
          </form>
        )}
      </div>
    </div>
  );
}
