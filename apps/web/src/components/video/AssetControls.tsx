"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { formatClock, parseClock } from "@/lib/live/model";
import { deleteVideo, updateVideo } from "@/lib/video-actions";

/** Dönüştürme sürerken sayfayı birkaç saniyede bir yeniler. */
export function StatusPoller({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => router.refresh(), 3000);
    return () => window.clearInterval(id);
  }, [active, router]);
  return null;
}

/** Maç saati başlangıcı (offset) ve videoyu silme. */
export function AssetControls({ assetId, offsetS }: { assetId: string; offsetS: number }) {
  const t = useTranslations("video");
  const router = useRouter();
  const [offset, setOffset] = useState(formatClock(offsetS));
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function saveOffset(event: React.FormEvent) {
    event.preventDefault();
    const parsed = parseClock(offset);
    if (parsed === null) return setError(t("errors.offset"));
    const result = await updateVideo(assetId, { offset_s: parsed });
    setError(result.ok ? null : t("errors.generic", { code: result.error }));
    router.refresh();
  }

  async function remove() {
    if (!confirming) return setConfirming(true);
    const result = await deleteVideo(assetId);
    if (!result.ok) return setError(t("errors.generic", { code: result.error }));
    router.push("/video");
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <form onSubmit={(e) => void saveOffset(e)} className="flex items-end gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink-2">{t("offset")}</span>
          <input
            value={offset}
            inputMode="numeric"
            onChange={(e) => setOffset(e.target.value)}
            className="min-h-11 w-24 rounded-md border border-line bg-surface px-2 tabular-nums"
          />
        </label>
        <button type="submit" className="min-h-11 rounded-md border border-line px-3 text-sm">
          {t("saveOffset")}
        </button>
      </form>
      <button
        type="button"
        onClick={() => void remove()}
        className="min-h-11 rounded-md border border-neg px-3 text-sm text-neg"
      >
        {confirming ? t("confirmDeleteVideo") : t("deleteVideo")}
      </button>
      {error ? (
        <p role="alert" className="text-sm text-neg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
