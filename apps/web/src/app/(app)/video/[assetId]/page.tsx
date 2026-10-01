import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { AssetControls, StatusPoller } from "@/components/video/AssetControls";
import { VideoWorkspace } from "@/components/video/VideoWorkspace";
import { getAsset, getFixture, getMatchSetPieces, liveAccess, listClips } from "@/lib/live-data";
import { listRoutines } from "@/lib/routines";

export default async function VideoAssetPage({
  params,
  searchParams,
}: {
  params: Promise<{ assetId: string }>;
  searchParams: Promise<{ clip?: string }>;
}) {
  const { assetId } = await params;
  const { clip } = await searchParams;
  const t = await getTranslations("video");
  const tStates = await getTranslations("states");
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
  const asset = await getAsset(assetId);
  if (asset.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={asset} />
      </>
    );
  }
  const a = asset.data;
  const [fixture, setPieces, clips, routines] = await Promise.all([
    a.match_id ? getFixture(a.match_id) : Promise.resolve(null),
    a.match_id ? getMatchSetPieces(a.match_id) : Promise.resolve(null),
    listClips({ asset_id: a.id }),
    access.read ? listRoutines(undefined, false) : Promise.resolve(null),
  ]);
  const f = fixture?.status === "ok" ? fixture.data : null;

  return (
    <>
      <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
        <Link href="/video" className="underline-offset-2 hover:underline">
          {t("title")}
        </Link>
      </nav>
      <PageTitle
        sub={
          f ? (
            <span className="inline-flex flex-wrap items-center gap-2">
              {t("week", { week: f.week ?? 0 })}
              <TeamBadge code={f.home.code} name={f.home.name} />
              {f.home.name} – <TeamBadge code={f.away.code} name={f.away.name} />
              {f.away.name}
            </span>
          ) : (
            t("noMatch")
          )
        }
      >
        {a.title}
      </PageTitle>
      <StatusPoller active={a.status === "uploading" || a.status === "processing"} />
      {access.tag ? (
        <div className="mb-4">
          <AssetControls assetId={a.id} offsetS={a.offset_s} />
        </div>
      ) : null}
      {a.status === "ready" ? (
        <VideoWorkspace
          assetId={a.id}
          offsetS={a.offset_s}
          durationS={a.duration_s}
          clips={clips.status === "ok" ? clips.data : []}
          setPieces={setPieces?.status === "ok" ? setPieces.data : []}
          routineNames={
            routines?.status === "ok"
              ? Object.fromEntries(routines.data.map((r) => [r.id, r.name]))
              : {}
          }
          canEdit={access.tag}
          initialClipId={clip}
        />
      ) : (
        <div data-testid="video-status" data-status={a.status}>
          {a.status === "failed" ? (
            <EmptyState
              title={t("failedTitle")}
              description={t("failed", { error: a.error ?? "" })}
            />
          ) : (
            <EmptyState title={t(`status.${a.status}`)} description={t("processing")} />
          )}
        </div>
      )}
    </>
  );
}
