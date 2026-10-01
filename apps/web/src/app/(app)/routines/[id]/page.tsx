import { cn, EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { RoutineEditor } from "@/components/routines/RoutineEditor";
import { RoutineStatsPanel } from "@/components/routines/RoutineStats";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { RoutineClips } from "@/components/video/RoutineClips";
import { restoreVersion, setArchived } from "@/lib/routine-actions";
import type { EditorDoc } from "@/lib/routine-editor";
import {
  getRoutine,
  getVersion,
  getVersions,
  routineAccess,
  type RoutineVersion,
  toDiagram,
} from "@/lib/routines";

type Search = { v?: string; created?: string; restored?: string; error?: string };

function toDoc(v: RoutineVersion): EditorDoc {
  return {
    name: v.name,
    side: v.side,
    notes: v.notes,
    whenToUse: v.when_to_use,
    diagram: toDiagram(v.diagram),
  };
}

export default async function RoutinePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const search = await searchParams;
  const t = await getTranslations("routines");
  const tStates = await getTranslations("states");
  const tType = await getTranslations("analysis.spType");
  const format = await getFormatter();
  const access = await routineAccess();
  if (!access.read) {
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
  const [routine, versions] = await Promise.all([getRoutine(id), getVersions(id)]);
  if (routine.status !== "ok") {
    return (
      <>
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={routine} />
      </>
    );
  }
  const r = routine.data;
  const requested = Number(search.v);
  const viewingOld =
    Number.isInteger(requested) && requested >= 1 && requested !== r.current_version;
  const old = viewingOld ? await getVersion(id, requested) : null;
  if (old && old.status !== "ok") {
    return (
      <>
        <PageTitle>{r.name}</PageTitle>
        <NotLoaded result={old} />
      </>
    );
  }
  const shown = old?.status === "ok" ? old.data : r.version;
  const editable = access.edit && !r.archived && !viewingOld;
  const versionList = versions.status === "ok" ? versions.data : [];

  return (
    <>
      <nav className="mb-2 text-sm">
        <Link href="/routines" className="text-ink-2 underline-offset-2 hover:underline">
          ← {t("back")}
        </Link>
      </nav>
      <PageTitle
        sub={
          <span className="flex flex-wrap gap-x-2">
            <span>{tType(r.sp_type)}</span>
            {r.is_defensive ? <span>· {t("defensive")}</span> : null}
            <span>· {t("versionShort", { version: shown.version })}</span>
            {r.from_template ? <span>· {t("fromTemplate")}</span> : null}
            {r.archived ? (
              <span className="rounded bg-ink-3/15 px-1.5 text-xs font-medium">
                {t("archivedBadge")}
              </span>
            ) : null}
          </span>
        }
      >
        {shown.name}
      </PageTitle>

      {search.created ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm">
          {t("notices.created")}
        </p>
      ) : null}
      {search.restored ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm">
          {t("notices.restored", { version: search.restored })}
        </p>
      ) : null}
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      {r.archived ? (
        <p className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-sm">
          {t("notices.archived")}
        </p>
      ) : null}
      {viewingOld ? (
        <div
          className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-accent bg-accent/10 px-3 py-2 text-sm"
          data-testid="old-version"
        >
          <span>
            {t("notices.oldVersion", { version: shown.version, current: r.current_version })}
          </span>
          <Link href={`/routines/${id}`} className={btn}>
            {t("versions.backToCurrent")}
          </Link>
          {access.edit && !r.archived ? (
            <form action={restoreVersion}>
              <input type="hidden" name="routineId" value={id} />
              <input type="hidden" name="version" value={shown.version} />
              <input type="hidden" name="baseVersion" value={r.current_version} />
              <input
                type="hidden"
                name="message"
                value={t("versions.restoreMessage", { version: shown.version })}
              />
              <button type="submit" className={btnPrimary} data-testid="restore">
                {t("versions.restore", { version: shown.version })}
              </button>
            </form>
          ) : null}
        </div>
      ) : null}

      <RoutineEditor
        key={`${id}:${viewingOld ? shown.version : "current"}:${search.restored ?? ""}`}
        routineId={id}
        initialDoc={toDoc(shown)}
        baseVersion={r.current_version}
        editable={editable}
        exportBase={`/routines/${id}/versions/${shown.version}/export`}
      />

      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <section
          aria-labelledby="versions-title"
          className="rounded-lg border border-line bg-surface p-3"
        >
          <h2 id="versions-title" className="mb-2 font-condensed text-base font-semibold">
            {t("versions.title")}
          </h2>
          {versions.status !== "ok" ? (
            <NotLoaded result={versions} />
          ) : (
            <>
              <ol
                className="mb-3 flex flex-col divide-y divide-line text-sm"
                data-testid="version-list"
              >
                {[...versionList].reverse().map((v) => (
                  <li key={v.version} className="flex flex-wrap items-baseline gap-x-2 py-2">
                    <Link
                      href={
                        v.version === r.current_version
                          ? `/routines/${id}`
                          : `/routines/${id}?v=${v.version}`
                      }
                      aria-current={v.version === shown.version ? "true" : undefined}
                      className={cn(
                        "font-medium tabular-nums underline-offset-2 hover:underline",
                        v.version === shown.version && "text-pri",
                      )}
                    >
                      {t("versionShort", { version: v.version })}
                    </Link>
                    <span className="text-ink-2">
                      {v.message ||
                        (v.version === 1 ? t("versions.first") : t("versions.noMessage"))}
                    </span>
                    <span className="ml-auto text-xs text-ink-3">
                      {v.created_by?.name ?? t("versions.unknownUser")} ·{" "}
                      {format.dateTime(new Date(v.created_at), {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </span>
                  </li>
                ))}
              </ol>
              {versionList.length > 1 ? (
                <form action={`/routines/${id}/compare`} className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    {t("compare.from")}
                    <select
                      name="a"
                      defaultValue={String(r.current_version - 1)}
                      className={inputCls}
                    >
                      {versionList.map((v) => (
                        <option key={v.version} value={v.version}>
                          {t("versionShort", { version: v.version })}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    {t("compare.to")}
                    <select name="b" defaultValue={String(r.current_version)} className={inputCls}>
                      {versionList.map((v) => (
                        <option key={v.version} value={v.version}>
                          {t("versionShort", { version: v.version })}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="submit" className={btn} data-testid="compare">
                    {t("compare.submit")}
                  </button>
                </form>
              ) : (
                <p className="text-xs text-ink-3">{t("compare.needTwo")}</p>
              )}
            </>
          )}
        </section>
        <div className="flex flex-col gap-4">
          <RoutineStatsPanel stats={r.stats} />
          <RoutineClips routineId={id} />
          {access.edit ? (
            <form
              action={setArchived}
              className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
            >
              <input type="hidden" name="routineId" value={id} />
              <input type="hidden" name="archived" value={r.archived ? "false" : "true"} />
              <p className="text-sm text-ink-2">
                {r.archived ? t("archive.restoreHelp") : t("archive.help")}
              </p>
              <button type="submit" className={btn} data-testid="archive">
                {r.archived ? t("archive.unarchive") : t("archive.archive")}
              </button>
            </form>
          ) : null}
        </div>
      </div>
    </>
  );
}
