"use client";

import { TeamBadge } from "@kurgu/ui";
import type Hls from "hls.js";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { formatClock } from "@/lib/live/model";
import { createClip, deleteClip, updateClip } from "@/lib/video-actions";

export interface WorkspaceClip {
  id: string;
  start_s: number;
  end_s: number;
  title: string;
  set_piece: { id: string } | null;
}

export interface WorkspaceSetPiece {
  id: string;
  team_code: string;
  period: number;
  start_time_s: number;
  sp_type: string;
  outcome: string | null;
  routine_id: string | null;
  source: string;
}

interface Props {
  assetId: string;
  offsetS: number;
  durationS: number | null;
  clips: WorkspaceClip[];
  setPieces: WorkspaceSetPiece[];
  routineNames: Record<string, string>;
  canEdit: boolean;
  initialClipId?: string;
}

function seconds(value: string): number | null {
  const n = Number(value.replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 10) / 10 : null;
}

function range(start: number, end: number) {
  return `${formatClock(start)}–${formatClock(end)}`;
}

/** HLS oynatıcı, klip kesme ve duran topa bağlama (SPEC §13.1 Video merkezi, A-62). */
export function VideoWorkspace({
  assetId,
  offsetS,
  durationS,
  clips,
  setPieces,
  routineNames,
  canEdit,
  initialClipId,
}: Props) {
  const t = useTranslations("video");
  const tA = useTranslations("analysis");
  const tLive = useTranslations("live");
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);
  const [ready, setReady] = useState(false);
  const [manifest, setManifest] = useState(false);
  const [playerError, setPlayerError] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [title, setTitle] = useState("");
  const [setPieceId, setSetPieceId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const src = `/api/video/assets/${assetId}/playlist`;
    let hls: Hls | null = null;
    let cancelled = false;
    const onReady = () => setReady(true);
    video.addEventListener("loadedmetadata", onReady);
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
    } else {
      void import("hls.js").then(({ default: HlsJs }) => {
        if (cancelled) return;
        if (!HlsJs.isSupported()) {
          setPlayerError(true);
          return;
        }
        hls = new HlsJs();
        hls.on(HlsJs.Events.MANIFEST_PARSED, () => setManifest(true));
        hls.on(HlsJs.Events.ERROR, (_event, data) => {
          if (data.fatal) setPlayerError(true);
        });
        hls.loadSource(src);
        hls.attachMedia(video);
      });
    }
    return () => {
      cancelled = true;
      video.removeEventListener("loadedmetadata", onReady);
      hls?.destroy();
    };
  }, [assetId]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTime = () => {
      if (stopAt.current !== null && video.currentTime >= stopAt.current) {
        video.pause();
        stopAt.current = null;
      }
    };
    video.addEventListener("timeupdate", onTime);
    return () => video.removeEventListener("timeupdate", onTime);
  }, []);

  function seek(to: number, until: number | null = null) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, to);
    stopAt.current = until;
    if (until !== null) void video.play().catch(() => undefined);
  }

  useEffect(() => {
    const clip = clips.find((c) => c.id === initialClipId);
    if (ready && clip) seek(clip.start_s, clip.end_s);
    // Yalnızca oynatıcı hazır olduğunda bir kez.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const now = () => Math.round((videoRef.current?.currentTime ?? 0) * 10) / 10;
  const label = (sp: WorkspaceSetPiece) =>
    [
      `${formatClock(sp.start_time_s)} ${tLive(`periodShort.${sp.period}`)}`,
      sp.team_code,
      tA(`spType.${sp.sp_type}`),
      sp.outcome ? tA(`outcome.${sp.outcome}`) : null,
      sp.routine_id ? (routineNames[sp.routine_id] ?? null) : null,
    ]
      .filter(Boolean)
      .join(" · ");
  const byId = new Map(setPieces.map((sp) => [sp.id, sp]));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const s = seconds(start);
    const e = seconds(end);
    if (s === null || e === null || e <= s) return setError(t("errors.range"));
    setSaving(true);
    const result = await createClip({
      asset_id: assetId,
      start_s: s,
      end_s: e,
      title: title.trim(),
      set_piece_id: setPieceId || null,
    });
    setSaving(false);
    if (!result.ok) return setError(t("errors.generic", { code: result.error }));
    setStart("");
    setEnd("");
    setTitle("");
    setSetPieceId("");
    router.refresh();
  }

  async function relink(clip: WorkspaceClip, value: string) {
    const result = await updateClip(clip.id, assetId, { set_piece_id: value || null });
    if (!result.ok) setError(t("errors.generic", { code: result.error }));
    router.refresh();
  }

  async function remove(clip: WorkspaceClip) {
    if (confirming !== clip.id) return setConfirming(clip.id);
    setConfirming(null);
    const result = await deleteClip(clip.id, assetId);
    if (!result.ok) setError(t("errors.generic", { code: result.error }));
    router.refresh();
  }

  const input = "min-h-11 rounded-md border border-line bg-surface px-2";
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-3">
        <video
          ref={videoRef}
          controls
          playsInline
          preload="metadata"
          className="aspect-video w-full rounded-lg bg-black"
          data-testid="video-player"
          data-ready={ready}
          data-manifest={manifest || ready}
          aria-label={t("player")}
        />
        {playerError ? (
          <p role="alert" className="text-sm text-neg">
            {t("errors.player")}
          </p>
        ) : null}
        {canEdit ? (
          <form
            onSubmit={(e) => void save(e)}
            className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
            data-testid="clip-form"
          >
            <h2 className="font-condensed text-lg font-semibold">{t("newClip")}</h2>
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink-2">{t("start")}</span>
                <input
                  value={start}
                  inputMode="decimal"
                  onChange={(e) => setStart(e.target.value)}
                  className={`${input} w-24 tabular-nums`}
                />
              </label>
              <button
                type="button"
                onClick={() => setStart(String(now()))}
                className="min-h-11 rounded-md border border-line px-3 text-sm"
              >
                {t("markStart")}
              </button>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink-2">{t("end")}</span>
                <input
                  value={end}
                  inputMode="decimal"
                  onChange={(e) => setEnd(e.target.value)}
                  className={`${input} w-24 tabular-nums`}
                />
              </label>
              <button
                type="button"
                onClick={() => setEnd(String(now()))}
                className="min-h-11 rounded-md border border-line px-3 text-sm"
              >
                {t("markEnd")}
              </button>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-ink-2">{t("clipTitle")}</span>
              <input
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
                className={input}
              />
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex grow flex-col gap-1 text-sm">
                <span className="text-ink-2">{t("setPiece")}</span>
                <select
                  value={setPieceId}
                  onChange={(e) => setSetPieceId(e.target.value)}
                  className={input}
                >
                  <option value="">{t("noSetPiece")}</option>
                  {setPieces.map((sp) => (
                    <option key={sp.id} value={sp.id}>
                      {label(sp)}
                    </option>
                  ))}
                </select>
              </label>
              {setPieceId ? (
                <button
                  type="button"
                  onClick={() => {
                    const sp = byId.get(setPieceId);
                    if (sp) seek(offsetS + sp.start_time_s - 5);
                  }}
                  className="min-h-11 rounded-md border border-line px-3 text-sm"
                >
                  {t("goToSetPiece")}
                </button>
              ) : null}
            </div>
            {setPieces.length === 0 ? (
              <p className="text-xs text-ink-3">{t("noSetPieces")}</p>
            ) : null}
            <p className="text-xs text-ink-3">{t("syncHelp")}</p>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={saving}
                className="min-h-11 rounded-md bg-pri px-4 font-medium text-brand-ink disabled:opacity-50"
              >
                {t("saveClip")}
              </button>
              {error ? (
                <p role="alert" className="text-sm text-neg">
                  {error}
                </p>
              ) : null}
            </div>
          </form>
        ) : null}
      </div>

      <section aria-labelledby="clips-title" className="flex flex-col gap-2">
        <h2 id="clips-title" className="font-condensed text-lg font-semibold">
          {t("clips", { count: clips.length })}
        </h2>
        {durationS ? (
          <p className="text-xs text-ink-3">{t("duration", { value: formatClock(durationS) })}</p>
        ) : null}
        {clips.length === 0 ? (
          <p className="rounded-md border border-dashed border-line p-4 text-sm text-ink-2">
            {t("noClips")}
          </p>
        ) : (
          <ol className="flex flex-col gap-2" data-testid="clips">
            {clips.map((clip) => {
              const sp = clip.set_piece ? byId.get(clip.set_piece.id) : undefined;
              return (
                <li
                  key={clip.id}
                  data-clip-id={clip.id}
                  className="flex flex-col gap-2 rounded-md border border-line bg-surface p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => seek(clip.start_s, clip.end_s)}
                      className="min-h-11 rounded-md bg-pri px-3 font-medium text-brand-ink"
                    >
                      {t("play")}
                    </button>
                    <span className="font-medium">{clip.title || t("untitled")}</span>
                    <span className="tabular-nums text-ink-2">
                      {range(clip.start_s, clip.end_s)}
                    </span>
                  </div>
                  {sp ? (
                    <p className="flex items-center gap-2 text-ink-2" data-testid="clip-set-piece">
                      <TeamBadge code={sp.team_code} name={sp.team_code} />
                      {label(sp)}
                    </p>
                  ) : null}
                  {canEdit ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="sr-only" htmlFor={`relink-${clip.id}`}>
                        {t("setPiece")}
                      </label>
                      <select
                        id={`relink-${clip.id}`}
                        value={clip.set_piece?.id ?? ""}
                        onChange={(e) => void relink(clip, e.target.value)}
                        className={`${input} max-w-full grow text-xs`}
                      >
                        <option value="">{t("noSetPiece")}</option>
                        {setPieces.map((option) => (
                          <option key={option.id} value={option.id}>
                            {label(option)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void remove(clip)}
                        className="min-h-11 rounded-md border border-line px-3 text-xs"
                      >
                        {confirming === clip.id ? tLive("confirmDelete") : tLive("delete")}
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}
