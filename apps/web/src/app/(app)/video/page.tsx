import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { StatusPoller } from "@/components/video/AssetControls";
import { VideoUpload, type MatchOption } from "@/components/video/VideoUpload";
import { liveAccess, listAssets } from "@/lib/live-data";
import { clubFixtures } from "@/lib/live-fixtures";

export default async function VideoPage() {
  const t = await getTranslations("video");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  const access = await liveAccess();
  if (!access.tag && !access.read) {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const [assets, fixtures] = await Promise.all([listAssets(), clubFixtures()]);
  if (assets.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={assets} />
      </>
    );
  }
  const matches: MatchOption[] =
    fixtures.status === "ok"
      ? [...fixtures.data.played, ...fixtures.data.upcoming].map((f) => ({
          id: f.id,
          label: `${t("week", { week: f.week ?? 0 })} · ${f.home.code}–${f.away.code}`,
        }))
      : [];
  const matchLabel = new Map(matches.map((m) => [m.id, m.label]));
  const busy = assets.data.some((a) => a.status === "uploading" || a.status === "processing");

  return (
    <>
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      <StatusPoller active={busy} />
      {access.tag ? (
        <Section id="video-upload-title" title={t("uploadTitle")}>
          <VideoUpload matches={matches} />
        </Section>
      ) : null}
      <Section id="video-list-title" title={t("library")}>
        {assets.data.length === 0 ? (
          <EmptyState title={t("emptyTitle")} description={t("empty")} />
        ) : (
          <ol className="flex flex-col gap-2" data-testid="video-assets">
            {assets.data.map((asset) => (
              <li key={asset.id}>
                <Link
                  href={`/video/${asset.id}`}
                  data-status={asset.status}
                  className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface p-3 hover:border-pri focus-visible:outline-2 focus-visible:outline-focus"
                >
                  <span className="font-medium">{asset.title}</span>
                  <span className="text-xs text-ink-2">
                    {asset.match_id
                      ? (matchLabel.get(asset.match_id) ?? t("linkedMatch"))
                      : t("noMatch")}
                  </span>
                  <span className="text-xs text-ink-3 tabular-nums">
                    {format.dateTime(new Date(asset.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </span>
                  <span className="ml-auto rounded bg-bg px-2 py-0.5 text-xs">
                    {t(`status.${asset.status}`)}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </>
  );
}
