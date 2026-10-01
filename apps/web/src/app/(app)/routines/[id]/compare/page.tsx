import { type Diagram, diffDiagrams, type DiagramDiff, roleLabel, viewXMin } from "@kurgu/pitch";
import { EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle } from "@/components/analysis/States";
import { BoardView } from "@/components/routines/board";
import { getRoutine, getVersion, routineAccess, toDiagram } from "@/lib/routines";

const DIFF_KEYS = [
  "playersAdded",
  "playersRemoved",
  "playersMoved",
  "playersChanged",
  "linesAdded",
  "linesRemoved",
  "linesChanged",
  "zonesAdded",
  "zonesRemoved",
  "zonesChanged",
] as const;

function describe(id: string, a: Diagram, b: Diagram, locale: string): string {
  const p = b.players.find((x) => x.id === id) ?? a.players.find((x) => x.id === id);
  if (p) {
    const role = roleLabel(p.team, p.role, locale);
    return p.number != null ? `${p.number} · ${role}` : role;
  }
  const z = b.zones.find((x) => x.id === id) ?? a.zones.find((x) => x.id === id);
  if (z?.label) return z.label;
  return id;
}

/** Aynı etiketleri birleştirir: "Savunmacı ×7". */
function summarize(labels: string[]): string {
  const counts = new Map<string, number>();
  for (const l of labels) counts.set(l, (counts.get(l) ?? 0) + 1);
  return [...counts].map(([l, n]) => (n > 1 ? `${l} ×${n}` : l)).join(", ");
}

export default async function ComparePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { id } = await params;
  const { a: rawA, b: rawB } = await searchParams;
  const t = await getTranslations("routines");
  const tStates = await getTranslations("states");
  const locale = await getLocale();
  const access = await routineAccess();
  if (!access.read) {
    return (
      <>
        <PageTitle>{t("compare.title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const routine = await getRoutine(id);
  if (routine.status !== "ok") {
    return (
      <>
        <PageTitle>{t("compare.title")}</PageTitle>
        <NotLoaded result={routine} />
      </>
    );
  }
  const current = routine.data.current_version;
  const parse = (raw: string | undefined, fallback: number) => {
    const n = Number(raw);
    return Number.isInteger(n) && n >= 1 && n <= current ? n : fallback;
  };
  const va = parse(rawA, Math.max(1, current - 1));
  const vb = parse(rawB, current);
  const [a, b] = await Promise.all([getVersion(id, va), getVersion(id, vb)]);
  if (a.status !== "ok" || b.status !== "ok") {
    return (
      <>
        <PageTitle>{t("compare.title")}</PageTitle>
        <NotLoaded result={a.status !== "ok" ? a : (b as Exclude<typeof b, { status: "ok" }>)} />
      </>
    );
  }
  const da = toDiagram(a.data.diagram);
  const db = toDiagram(b.data.diagram);
  const diff: DiagramDiff = diffDiagrams(da, db);
  const xMin = viewXMin(da, db);
  const meta: string[] = [];
  if (a.data.name !== b.data.name)
    meta.push(t("compare.meta.name", { from: a.data.name, to: b.data.name }));
  if (a.data.side !== b.data.side) meta.push(t("compare.meta.side"));
  if (a.data.notes !== b.data.notes) meta.push(t("compare.meta.notes"));
  if (a.data.when_to_use !== b.data.when_to_use) meta.push(t("compare.meta.whenToUse"));
  if (diff.framesBefore !== diff.framesAfter) {
    meta.push(t("compare.meta.frames", { from: diff.framesBefore, to: diff.framesAfter }));
  }
  const groups = DIFF_KEYS.filter((k) => diff[k].length > 0);

  return (
    <>
      <nav className="mb-2 text-sm">
        <Link href={`/routines/${id}`} className="text-ink-2 underline-offset-2 hover:underline">
          ← {routine.data.name}
        </Link>
      </nav>
      <PageTitle sub={t("compare.subtitle", { a: va, b: vb })}>{t("compare.title")}</PageTitle>
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        {[
          { v: a.data, d: da },
          { v: b.data, d: db },
        ].map(({ v, d }) => (
          <figure
            key={v.version}
            className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
          >
            <figcaption className="font-condensed text-base font-semibold">
              {t("versionShort", { version: v.version })} · {v.name}
              {v.message ? (
                <span className="block text-xs font-normal text-ink-2">{v.message}</span>
              ) : null}
            </figcaption>
            <BoardView
              diagram={d}
              xMin={xMin}
              label={t("thumb", {
                name: `${v.name} (${t("versionShort", { version: v.version })})`,
              })}
              gkLabel={t("gkShort")}
              className="block w-full rounded-md border border-line"
            />
          </figure>
        ))}
      </div>
      <section
        aria-labelledby="diff-title"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <h2 id="diff-title" className="mb-2 font-condensed text-base font-semibold">
          {t("compare.changes")}
        </h2>
        {groups.length === 0 && meta.length === 0 ? (
          <p className="text-sm text-ink-2" data-testid="diff-empty">
            {t("compare.none")}
          </p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm" data-testid="diff-list">
            {meta.map((m) => (
              <li key={m}>{m}</li>
            ))}
            {groups.map((k) => (
              <li key={k} data-diff={k}>
                <span className="font-medium">{t(`compare.diff.${k}`, { n: diff[k].length })}</span>
                {k.startsWith("players") || k.startsWith("zones") ? (
                  <span className="text-ink-2">
                    {": "}
                    {summarize(diff[k].map((x) => describe(x, da, db, locale)))}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
