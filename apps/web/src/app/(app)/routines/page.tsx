import { type Diagram, viewXMin } from "@kurgu/pitch";
import { cn, EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { BoardView } from "@/components/routines/board";
import { RoutineStatsLine } from "@/components/routines/RoutineStats";
import { btn, btnPrimary, btnToggle, inputCls } from "@/components/routines/styles";
import { addTemplate, createRoutine } from "@/lib/routine-actions";
import { getTemplates, listRoutines, routineAccess, type SpType, toDiagram } from "@/lib/routines";

const SP_TYPES: SpType[] = ["corner", "free_kick", "throw_in"];

type Search = { tab?: string; type?: string; archived?: string; error?: string };

function href(current: Search, changes: Partial<Search>): string {
  const params = new URLSearchParams();
  const next = { ...current, ...changes, error: undefined };
  for (const [k, v] of Object.entries(next)) if (v) params.set(k, v);
  const query = params.toString();
  return query ? `/routines?${query}` : "/routines";
}

function Thumb({ diagram, label }: { diagram: Diagram; label: string }) {
  return (
    <BoardView
      diagram={diagram}
      xMin={viewXMin(diagram)}
      label={label}
      className="block w-full rounded-md border border-line"
    />
  );
}

export default async function RoutinesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("routines");
  const tStates = await getTranslations("states");
  const tType = await getTranslations("analysis.spType");
  const format = await getFormatter();
  const search = await searchParams;
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
  const tab = search.tab === "templates" ? "templates" : "library";
  const type = SP_TYPES.find((x) => x === search.type);
  const archived = search.archived === "1";

  const tabLink = (key: "library" | "templates") => (
    <Link
      key={key}
      href={href({}, { tab: key === "templates" ? "templates" : undefined })}
      aria-current={tab === key ? "page" : undefined}
      className={btnToggle(tab === key)}
      data-testid={`tab-${key}`}
    >
      {t(`tabs.${key}`)}
    </Link>
  );

  return (
    <>
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      <nav aria-label={t("tabs.label")} className="mb-6 flex gap-2">
        {tabLink("library")}
        {tabLink("templates")}
      </nav>
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      {tab === "templates" ? (
        <Templates canEdit={access.edit} />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <nav aria-label={t("filters.type")} className="flex flex-wrap gap-2">
              <Link
                href={href(search, { type: undefined })}
                aria-current={!type ? "true" : undefined}
                className={btnToggle(!type)}
              >
                {t("filters.all")}
              </Link>
              {SP_TYPES.map((x) => (
                <Link
                  key={x}
                  href={href(search, { type: x })}
                  aria-current={type === x ? "true" : undefined}
                  className={btnToggle(type === x)}
                >
                  {tType(x)}
                </Link>
              ))}
            </nav>
            <Link
              href={href(search, { archived: archived ? undefined : "1" })}
              aria-current={archived ? "true" : undefined}
              className={btnToggle(archived)}
              data-testid="filter-archived"
            >
              {t("filters.archived")}
            </Link>
          </div>
          {access.edit && !archived ? (
            <details className="mb-6 rounded-lg border border-line bg-surface p-3">
              <summary className="cursor-pointer text-sm font-medium">{t("create.title")}</summary>
              <form
                action={createRoutine}
                className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto_auto_auto_auto] sm:items-end"
              >
                <label className="flex flex-col gap-1 text-xs text-ink-2">
                  {t("fields.name")}
                  <input name="name" required maxLength={120} className={inputCls} />
                </label>
                <label className="flex flex-col gap-1 text-xs text-ink-2">
                  {t("fields.type")}
                  <select name="spType" defaultValue={type ?? "corner"} className={inputCls}>
                    {SP_TYPES.map((x) => (
                      <option key={x} value={x}>
                        {tType(x)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-ink-2">
                  {t("fields.side")}
                  <select name="side" defaultValue="right" className={inputCls}>
                    <option value="right">{t("side.right")}</option>
                    <option value="left">{t("side.left")}</option>
                    <option value="">{t("side.none")}</option>
                  </select>
                </label>
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" name="defensive" className="size-5" />
                  {t("fields.defensive")}
                </label>
                <button type="submit" className={btnPrimary}>
                  {t("create.submit")}
                </button>
              </form>
            </details>
          ) : null}
          <Library type={type} archived={archived} canEdit={access.edit} format={format} />
        </>
      )}
    </>
  );
}

async function Library({
  type,
  archived,
  canEdit,
  format,
}: {
  type: SpType | undefined;
  archived: boolean;
  canEdit: boolean;
  format: Awaited<ReturnType<typeof getFormatter>>;
}) {
  const t = await getTranslations("routines");
  const tType = await getTranslations("analysis.spType");
  const routines = await listRoutines(type, archived);
  if (routines.status !== "ok") return <NotLoaded result={routines} />;
  if (routines.data.length === 0) {
    return (
      <EmptyState
        title={archived ? t("empty.archivedTitle") : t("empty.title")}
        description={archived ? t("empty.archived") : canEdit ? t("empty.edit") : t("empty.read")}
      />
    );
  }
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="routine-list">
      {routines.data.map((r) => (
        <li key={r.id} className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3">
          <Link href={`/routines/${r.id}`} className="group flex flex-col gap-2">
            <Thumb diagram={toDiagram(r.diagram)} label={t("thumb", { name: r.name })} />
            <span className="font-condensed text-lg font-semibold group-hover:underline">
              {r.name}
            </span>
          </Link>
          <p className="flex flex-wrap gap-x-2 text-xs text-ink-2">
            <span>{tType(r.sp_type)}</span>
            {r.side ? <span>· {t(`side.${r.side}`)}</span> : null}
            {r.is_defensive ? <span>· {t("defensive")}</span> : null}
            <span>· {t("versionShort", { version: r.current_version })}</span>
            <span>· {format.dateTime(new Date(r.updated_at), { dateStyle: "medium" })}</span>
          </p>
          <RoutineStatsLine stats={r.stats} />
        </li>
      ))}
    </ul>
  );
}

async function Templates({ canEdit }: { canEdit: boolean }) {
  const t = await getTranslations("routines");
  const tType = await getTranslations("analysis.spType");
  const templates = await getTemplates();
  if (templates.status !== "ok") return <NotLoaded result={templates} />;
  if (templates.data.length === 0) {
    return <EmptyState title={t("templates.emptyTitle")} description={t("templates.empty")} />;
  }
  return (
    <>
      <p className="mb-4 text-sm text-ink-2">{t("templates.intro")}</p>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="template-list">
        {templates.data.map((tpl) => (
          <li
            key={tpl.id}
            className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
            data-template={tpl.id}
          >
            <Thumb diagram={toDiagram(tpl.diagram)} label={t("thumb", { name: tpl.name })} />
            <h2 className="font-condensed text-lg font-semibold">{tpl.name}</h2>
            <p className="text-xs text-ink-2">
              {tType(tpl.sp_type)}
              {tpl.side ? ` · ${t(`side.${tpl.side}`)}` : ""}
              {tpl.is_defensive ? ` · ${t("defensive")}` : ""}
            </p>
            {tpl.when_to_use ? (
              <p className="text-sm">
                <span className="font-medium">{t("fields.whenToUse")}: </span>
                {tpl.when_to_use}
              </p>
            ) : null}
            {canEdit ? (
              <form action={addTemplate} className="mt-auto">
                <input type="hidden" name="templateId" value={tpl.id} />
                <button type="submit" className={cn(btn, "w-full")}>
                  {t("templates.add")}
                </button>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
