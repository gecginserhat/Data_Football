import { getTranslations } from "next-intl/server";
import { NotLoaded } from "@/components/analysis/States";
import { getConsent, getConsentText, listPrivacyRequests } from "@/lib/privacy";
import { PrivacyPanel } from "./PrivacyPanel";

/** Rıza ve veri sahibi hakları bölümü; verisini kendisi yükler (`#privacy` çapası). */
export async function PrivacySection({
  playerId,
  returnTo,
  error,
  saved,
}: {
  playerId: string;
  returnTo: "me" | "player";
  error?: string;
  saved?: string;
}) {
  const t = await getTranslations("privacy");
  const [status, text, requests] = await Promise.all([
    getConsent(playerId),
    getConsentText(),
    listPrivacyRequests(),
  ]);
  if (status.status === "forbidden") return null;
  return (
    <section aria-labelledby="privacy" className="mb-6 scroll-mt-20">
      <h2 id="privacy" className="mb-3 font-condensed text-lg font-semibold">
        {t("section")}
      </h2>
      {status.status !== "ok" ? (
        <NotLoaded result={status} />
      ) : text.status !== "ok" ? (
        <NotLoaded result={text} />
      ) : (
        <PrivacyPanel
          status={status.data}
          text={text.data}
          requests={requests.status === "ok" ? requests.data : []}
          returnTo={returnTo}
          error={error}
          saved={saved}
        />
      )}
    </section>
  );
}
