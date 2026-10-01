"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { parseClock } from "@/lib/live/model";
import { completeUpload, startUpload } from "@/lib/video-actions";

export interface MatchOption {
  id: string;
  label: string;
}

const TYPES: Record<string, "video/mp4" | "video/quicktime" | "video/x-matroska" | "video/webm"> = {
  mp4: "video/mp4",
  m4v: "video/mp4",
  mov: "video/quicktime",
  mkv: "video/x-matroska",
  webm: "video/webm",
};
const MAX_BYTES = 8 * 1024 ** 3;
const CONCURRENCY = 3;

function contentType(file: File) {
  const byType = Object.values(TYPES).find((t) => t === file.type);
  return byType ?? TYPES[file.name.split(".").pop()?.toLowerCase() ?? ""];
}

type Phase = "idle" | "uploading" | "finishing" | "error";

/** Parçalı yükleme: parçalar imzalı adreslere doğrudan, en çok üçü aynı anda gider (A-60). */
export function VideoUpload({ matches }: { matches: MatchOption[] }) {
  const t = useTranslations("video");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [matchId, setMatchId] = useState(matches[0]?.id ?? "");
  const [offset, setOffset] = useState("00:00");
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!file) return setError(t("errors.noFile"));
    const type = contentType(file);
    if (!type) return setError(t("errors.type"));
    if (file.size > MAX_BYTES) return setError(t("errors.size"));
    const offsetS = parseClock(offset);
    if (offsetS === null) return setError(t("errors.offset"));

    setPhase("uploading");
    setProgress(0);
    const started = await startUpload(
      {
        title: title.trim() || file.name,
        filename: file.name,
        content_type: type,
        size_bytes: file.size,
        match_id: matchId || null,
        offset_s: offsetS,
      },
      crypto.randomUUID(),
    );
    if (!started.ok) {
      setPhase("error");
      return setError(t("errors.generic", { code: started.error }));
    }
    const { asset, parts, part_size: partSize } = started.data;
    const etags: string[] = new Array(parts.length);
    let sent = 0;
    let next = 0;
    try {
      const worker = async () => {
        while (next < parts.length) {
          const part = parts[next++];
          if (!part) return;
          const chunk = file.slice((part.number - 1) * partSize, part.number * partSize);
          const response = await fetch(part.url, { method: "PUT", body: chunk });
          const etag = response.headers.get("ETag");
          if (!response.ok || !etag) throw new Error(`part ${part.number}: ${response.status}`);
          etags[part.number - 1] = etag;
          sent += chunk.size;
          setProgress(Math.round((sent / file.size) * 100));
        }
      };
      await Promise.all(Array.from({ length: Math.min(CONCURRENCY, parts.length) }, worker));
    } catch {
      setPhase("error");
      return setError(t("errors.part"));
    }
    setPhase("finishing");
    const done = await completeUpload(asset.id, etags);
    if (!done.ok) {
      setPhase("error");
      return setError(t("errors.generic", { code: done.error }));
    }
    router.push(`/video/${asset.id}`);
  }

  const busy = phase === "uploading" || phase === "finishing";
  return (
    <form
      onSubmit={(e) => void submit(e)}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
      data-testid="video-upload"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-2">{t("file")}</span>
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mkv"
            disabled={busy}
            onChange={(e) => {
              const picked = e.target.files?.[0] ?? null;
              setFile(picked);
              if (picked && !title) setTitle(picked.name.replace(/\.[^.]+$/, ""));
            }}
            className="min-h-11 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-2">{t("titleField")}</span>
          <input
            value={title}
            maxLength={200}
            disabled={busy}
            onChange={(e) => setTitle(e.target.value)}
            className="min-h-11 rounded-md border border-line bg-surface px-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-2">{t("match")}</span>
          <select
            value={matchId}
            disabled={busy}
            onChange={(e) => setMatchId(e.target.value)}
            className="min-h-11 rounded-md border border-line bg-surface px-2"
          >
            <option value="">{t("noMatch")}</option>
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-2">{t("offset")}</span>
          <input
            value={offset}
            inputMode="numeric"
            disabled={busy}
            onChange={(e) => setOffset(e.target.value)}
            className="min-h-11 w-32 rounded-md border border-line bg-surface px-2 tabular-nums"
          />
          <span className="text-xs text-ink-3">{t("offsetHelp")}</span>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy || !file}
          className="min-h-11 rounded-md bg-pri px-4 font-medium text-brand-ink disabled:opacity-50"
        >
          {t("upload")}
        </button>
        {busy ? (
          <span className="flex items-center gap-2 text-sm" role="status">
            <progress value={progress} max={100} className="w-40" aria-label={t("progress")} />
            <span className="tabular-nums">
              {phase === "finishing" ? t("finishing") : t("percent", { value: progress })}
            </span>
          </span>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-neg">
            {error}
          </p>
        ) : null}
      </div>
      <p className="text-xs text-ink-3">{t("limits")}</p>
    </form>
  );
}
