"use client";

import {
  type DiagramLine,
  type DiagramPlayer,
  type DiagramTeam,
  type LineKind,
  type Point,
  clampToBoard,
  curveThrough,
  interpolate,
  keyframe,
  pointOnCurve,
  ROLES,
  roleLabel,
  snap,
  type Snapshot,
} from "@kurgu/pitch";
import { cn } from "@kurgu/ui";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
  useTransition,
} from "react";
import { useStore } from "zustand";
import { saveRoutine } from "@/lib/routine-actions";
import {
  addFrame,
  addLine,
  addPlayer,
  addZone,
  type EditorDoc,
  mirror,
  moveLine,
  movePlayer,
  moveZone,
  nudge,
  removeFrame,
  removeSelection,
  sameDoc,
  type Selection,
  setBall,
  setFrameDuration,
  updateLine,
  updatePlayer,
  updateZone,
} from "@/lib/routine-editor";
import {
  BallShape,
  fromSvg,
  LineShape,
  lineGeometry,
  PitchMarkings,
  PLAYER_RADIUS,
  PlayerShape,
  toSvg,
  viewBox,
  ZoneShape,
} from "./board";
import { createEditorStore, type EditorStore, type Tool } from "./store";
import { btn, btnPrimary, btnToggle } from "./styles";

const ZONE_CODES = ["NP", "C6", "FP", "PS", "ED", "SH", "OT"];
const LINE_KINDS: LineKind[] = ["run", "ball_path", "screen"];
const TOOLS: { tool: Tool; key: string }[] = [
  { tool: "select", key: "v" },
  { tool: "player", key: "p" },
  { tool: "run", key: "r" },
  { tool: "ball_path", key: "b" },
  { tool: "screen", key: "s" },
  { tool: "zone", key: "z" },
];
const GRID_STEP = 1;
const NUDGE = 0.5;
const NUDGE_BIG = 2;

type Drag =
  | { kind: "player"; id: string }
  | { kind: "ball" }
  | { kind: "zone"; id: string; last: Point }
  | { kind: "line"; id: string; last: Point }
  | { kind: "from" | "to" | "curve"; id: string }
  | { kind: "draw"; tool: "run" | "ball_path" | "screen" | "zone"; start: Point; end: Point };

export interface RoutineEditorProps {
  routineId: string;
  initialDoc: EditorDoc;
  baseVersion: number;
  editable: boolean;
  /** Dışa aktarma bağlantısının temeli; `?format=pdf|png&lang=` eklenir. */
  exportBase: string;
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
}

function fmt(v: number): string {
  return v.toFixed(1);
}

/** Rutin editörü (SPEC §13.2): yarım saha SVG, araçlar, kareler, geri al / yinele, kayıt. */
export function RoutineEditor(props: RoutineEditorProps) {
  const [store] = useState(() => createEditorStore(props.initialDoc));
  return <EditorInner {...props} store={store} />;
}

function EditorInner({
  routineId,
  initialDoc,
  baseVersion: initialBase,
  editable,
  exportBase,
  store,
}: RoutineEditorProps & { store: EditorStore }) {
  const t = useTranslations("routines");
  const locale = useLocale();
  const router = useRouter();
  const doc = useStore(store, (s) => s.doc);
  const selection = useStore(store, (s) => s.selection);
  const tool = useStore(store, (s) => s.tool);
  const team = useStore(store, (s) => s.team);
  const role = useStore(store, (s) => s.role);
  const grid = useStore(store, (s) => s.grid);
  const frameRaw = useStore(store, (s) => s.frame);
  const apply = useStore(store, (s) => s.apply);
  const setUi = useStore(store, (s) => s.setUi);
  const canUndo = useStore(store.temporal, (s) => s.pastStates.length > 0);
  const canRedo = useStore(store.temporal, (s) => s.futureStates.length > 0);
  const undo = useCallback(() => store.temporal.getState().undo(), [store]);
  const redo = useCallback(() => store.temporal.getState().redo(), [store]);

  const [saved, setSaved] = useState(initialDoc);
  const [base, setBase] = useState(initialBase);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState<
    | { kind: "saved"; version: number }
    | { kind: "conflict"; current: number | null }
    | { kind: "error"; code: string }
    | null
  >(null);
  const [pending, startTransition] = useTransition();
  const [playT, setPlayT] = useState<number | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const diagram = doc.diagram;
  const frame = Math.min(frameRaw, diagram.frames.length);
  const dirty = !sameDoc(doc, saved);
  const playing = playT !== null;
  const interactive = editable && !playing;
  const step = grid ? GRID_STEP : 0;

  // Seçim, geri alma sonrası artık yoksa yok sayılır.
  const selected: Selection | null = (() => {
    if (!selection) return null;
    if (selection.kind === "ball") return diagram.ball || frame > 0 ? selection : null;
    const list =
      selection.kind === "player"
        ? diagram.players
        : selection.kind === "line"
          ? diagram.lines
          : diagram.zones;
    return list.some((x) => x.id === selection.id) ? selection : null;
  })();

  const snapshot: Snapshot = playing ? interpolate(diagram, playT) : keyframe(diagram, frame);
  const previous: Snapshot | null = frame > 0 && !playing ? keyframe(diagram, frame - 1) : null;

  // Kaydedilmemiş değişiklik varken sayfadan çıkış uyarısı.
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // Oynatma: kare süreleriyle zaman ilerler; hareket azaltma tercihinde kareler arası atlanır.
  useEffect(() => {
    if (!playing) return;
    const frames = diagram.frames;
    const duration = (i: number) => frames[i]?.duration_ms ?? 1000;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      let reached = 0;
      let timer: ReturnType<typeof setTimeout>;
      const advance = () => {
        reached += 1;
        setPlayT(reached > frames.length ? null : reached);
        if (reached <= frames.length) timer = setTimeout(advance, duration(reached));
      };
      timer = setTimeout(advance, duration(0));
      return () => clearTimeout(timer);
    }
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      setPlayT((current) => {
        if (current === null) return null;
        const i = Math.min(Math.floor(current), frames.length - 1);
        const next = current + dt / duration(i);
        return next >= frames.length ? null : next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, diagram.frames]);

  const toPitch = useCallback(
    (e: { clientX: number; clientY: number }): Point => {
      const svg = svgRef.current;
      if (!svg) return [0, 0];
      const ctm = svg.getScreenCTM();
      if (!ctm) return [0, 0];
      const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      const [x, y] = clampToBoard(fromSvg(p.x, p.y));
      return step ? [snap(x, step), snap(y, step)] : [x, y];
    },
    [step],
  );

  const select = (s: Selection | null) => setUi({ selection: s });

  // --- İşaretçi -----------------------------------------------------------------------------

  const startDrag = (e: ReactPointerEvent, d: Drag) => {
    if (!interactive) return;
    e.stopPropagation();
    svgRef.current?.setPointerCapture(e.pointerId);
    store.getState().beginDrag();
    setDrag(d);
  };

  const onBoardPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!interactive || e.button !== 0) return;
    const p = toPitch(e);
    if (tool === "player" && frame === 0) {
      let created: string | null = null;
      apply((d) => {
        const r = addPlayer(d, team, role, p);
        created = r.id;
        return r.doc;
      });
      if (created) select({ kind: "player", id: created });
      return;
    }
    if (tool === "run" || tool === "ball_path" || tool === "screen" || tool === "zone") {
      if (frame > 0) return;
      svgRef.current?.setPointerCapture(e.pointerId);
      setDrag({ kind: "draw", tool, start: p, end: p });
      return;
    }
    select(null);
  };

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const p = toPitch(e);
    const s = store.getState();
    switch (drag.kind) {
      case "player":
        s.apply((d) => movePlayer(d, drag.id, p, frame));
        break;
      case "ball":
        s.apply((d) => setBall(d, p, frame));
        break;
      case "zone":
        s.apply((d) => moveZone(d, drag.id, p[0] - drag.last[0], p[1] - drag.last[1]));
        setDrag({ ...drag, last: p });
        break;
      case "line":
        s.apply((d) => moveLine(d, drag.id, p[0] - drag.last[0], p[1] - drag.last[1]));
        setDrag({ ...drag, last: p });
        break;
      case "from":
        s.apply((d) => updateLine(d, drag.id, { from: p, player_id: null }));
        break;
      case "to":
        s.apply((d) => updateLine(d, drag.id, { to: p }));
        break;
      case "curve": {
        const line = s.doc.diagram.lines.find((l) => l.id === drag.id);
        if (line)
          s.apply((d) => updateLine(d, drag.id, { curve: curveThrough(line.from, line.to, p) }));
        break;
      }
      case "draw":
        setDrag({ ...drag, end: p });
        break;
    }
  };

  const onPointerUp = () => {
    if (!drag) return;
    if (drag.kind === "draw") {
      const { start, end } = drag;
      const long = Math.hypot(end[0] - start[0], end[1] - start[1]) >= 1;
      if (long) {
        let created: Selection | null = null;
        apply((d) => {
          if (drag.tool === "zone") {
            const r = addZone(d, start, end);
            if (r.id) created = { kind: "zone", id: r.id };
            return r.doc;
          }
          const r = addLine(d, drag.tool, start, end);
          if (r.id) created = { kind: "line", id: r.id };
          return r.doc;
        });
        if (created) select(created);
      }
    } else {
      store.getState().endDrag();
    }
    setDrag(null);
  };

  // --- Klavye -------------------------------------------------------------------------------

  const nudgeSelection = (dx: number, dy: number) => {
    if (!selected || !interactive) return;
    if (selected.kind === "player") {
      const at = snapshot.positions[selected.id];
      if (at) apply((d) => movePlayer(d, selected.id, nudge(at, dx, dy), frame));
    } else if (selected.kind === "ball") {
      const at = snapshot.ball;
      if (at) apply((d) => setBall(d, nudge(at, dx, dy), frame));
    } else if (frame === 0 && selected.kind === "line") {
      apply((d) => moveLine(d, selected.id, dx, dy));
    } else if (frame === 0 && selected.kind === "zone") {
      apply((d) => moveZone(d, selected.id, dx, dy));
    }
  };

  const onElementKey = (e: ReactKeyboardEvent) => {
    const amount = e.shiftKey ? NUDGE_BIG : step || NUDGE;
    // Tahtada yukarı = kaleye doğru (+x); sol = y artar (y = 0 sağ taç çizgisi).
    const moves: Record<string, [number, number]> = {
      ArrowUp: [amount, 0],
      ArrowDown: [-amount, 0],
      ArrowLeft: [0, amount],
      ArrowRight: [0, -amount],
    };
    const m = moves[e.key];
    if (m) {
      e.preventDefault();
      nudgeSelection(m[0], m[1]);
    } else if ((e.key === "Delete" || e.key === "Backspace") && selected && interactive) {
      e.preventDefault();
      if (frame === 0) apply((d) => removeSelection(d, selected), null);
    } else if (e.key === "Escape") {
      select(null);
      (e.target as HTMLElement).blur();
    }
  };

  type KeyLike = Pick<
    KeyboardEvent,
    "target" | "ctrlKey" | "metaKey" | "shiftKey" | "altKey" | "key" | "preventDefault"
  >;
  const onEditorKey = (e: KeyLike) => {
    if (isTyping(e.target)) return;
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();
    if (mod && key === "z" && !e.shiftKey) {
      e.preventDefault();
      undo();
    } else if (mod && ((key === "z" && e.shiftKey) || key === "y")) {
      e.preventDefault();
      redo();
    } else if (mod && key === "s") {
      e.preventDefault();
      if (editable && dirty) save(base);
    } else if (!mod && !e.altKey && interactive) {
      const match = TOOLS.find((x) => x.key === key);
      if (match) {
        setUi({ tool: match.tool });
      } else if (key === "m" && frame === 0) {
        apply(mirror);
      } else if (key === "g") {
        setUi({ grid: !grid });
      }
    }
  };

  // --- Kayıt --------------------------------------------------------------------------------

  const save = (baseVersion: number) => {
    const current = store.getState().doc;
    startTransition(async () => {
      const result = await saveRoutine(routineId, current, baseVersion, message);
      if (result.status === "ok") {
        setSaved(current);
        setBase(result.version);
        setMessage("");
        setNotice({ kind: "saved", version: result.version });
        router.refresh();
      } else if (result.status === "conflict") {
        setNotice({ kind: "conflict", current: result.currentVersion });
      } else {
        setNotice({ kind: "error", code: result.code });
      }
    });
  };

  // Odak sayfada (body) iken de kısayollar çalışsın: ör. tahtaya tıkladıktan sonra Ctrl+S.
  const keyRef = useRef(onEditorKey);
  useEffect(() => {
    keyRef.current = onEditorKey;
  });
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target === document.body) keyRef.current(e);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // --- Çizim --------------------------------------------------------------------------------

  const playerLabel = (p: DiagramPlayer) =>
    t("a11y.player", {
      team: t(`team.${p.team}`),
      number: p.number ?? "",
      role: roleLabel(p.team, p.role, locale),
      x: fmt(snapshot.positions[p.id]?.[0] ?? p.x),
      y: fmt(snapshot.positions[p.id]?.[1] ?? p.y),
    });
  const lineLabel = (l: DiagramLine) => t("a11y.line", { kind: t(`lineKind.${l.kind}`), id: l.id });

  const focusable = interactive ? 0 : -1;
  const isSelected = (kind: Selection["kind"], id?: string) =>
    selected?.kind === kind && (kind === "ball" || (selected as { id?: string }).id === id);

  const board = (
    <svg
      ref={svgRef}
      viewBox={viewBox()}
      className={cn(
        "block w-full touch-none select-none rounded-lg border border-line",
        interactive && tool !== "select" && frame === 0 ? "cursor-crosshair" : "",
      )}
      role="group"
      aria-label={t("board.label")}
      aria-describedby="routine-board-help"
      data-testid="routine-board"
      onPointerDown={onBoardPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <PitchMarkings />
      {grid ? <GridLines /> : null}
      {diagram.zones.map((z) => (
        <g
          key={z.id}
          tabIndex={frame === 0 ? focusable : -1}
          role="button"
          aria-label={t("a11y.zone", { label: z.label ?? z.id })}
          aria-pressed={isSelected("zone", z.id)}
          data-element={z.id}
          onFocus={() => select({ kind: "zone", id: z.id })}
          onKeyDown={onElementKey}
          onPointerDown={(e) => {
            if (tool !== "select" || frame > 0) return;
            select({ kind: "zone", id: z.id });
            startDrag(e, { kind: "zone", id: z.id, last: toPitch(e) });
          }}
          className={cn(
            "outline-none",
            frame === 0 && interactive && tool === "select" && "cursor-move",
          )}
        >
          <ZoneShape zone={z} />
          {isSelected("zone", z.id) ? <SelectionBox zone={z} /> : null}
        </g>
      ))}
      {diagram.lines.map((l) => (
        <g
          key={l.id}
          tabIndex={frame === 0 ? focusable : -1}
          role="button"
          aria-label={lineLabel(l)}
          aria-pressed={isSelected("line", l.id)}
          data-element={l.id}
          onFocus={() => select({ kind: "line", id: l.id })}
          onKeyDown={onElementKey}
          onPointerDown={(e) => {
            if (tool !== "select" || frame > 0) return;
            select({ kind: "line", id: l.id });
            startDrag(e, { kind: "line", id: l.id, last: toPitch(e) });
          }}
          className={cn(
            "outline-none",
            frame === 0 && interactive && tool === "select" && "cursor-move",
          )}
        >
          {/* Geniş, görünmez dokunma alanı */}
          <path d={lineGeometry(l).d} fill="none" stroke="transparent" strokeWidth={2.2} />
          <LineShape line={l} dimmed={frame > 0 || playing} />
        </g>
      ))}
      {previous
        ? diagram.players.map((p) => {
            const a = previous.positions[p.id];
            const b = snapshot.positions[p.id];
            if (!a || !b || (a[0] === b[0] && a[1] === b[1])) return null;
            const [ax, ay] = toSvg(a);
            const [bx, by] = toSvg(b);
            return (
              <g key={`trail-${p.id}`} aria-hidden="true" opacity={0.45}>
                <line
                  x1={ax}
                  y1={ay}
                  x2={bx}
                  y2={by}
                  stroke="var(--ink-3)"
                  strokeWidth={0.2}
                  strokeDasharray="0.6 0.5"
                />
                <circle
                  cx={ax}
                  cy={ay}
                  r={PLAYER_RADIUS}
                  fill="none"
                  stroke="var(--ink-3)"
                  strokeWidth={0.15}
                />
              </g>
            );
          })
        : null}
      {diagram.players.map((p) => {
        const at = snapshot.positions[p.id] ?? [p.x, p.y];
        return (
          <g
            key={p.id}
            tabIndex={focusable}
            role="button"
            aria-label={playerLabel(p)}
            aria-pressed={isSelected("player", p.id)}
            data-element={p.id}
            onFocus={() => select({ kind: "player", id: p.id })}
            onKeyDown={onElementKey}
            onPointerDown={(e) => {
              if (tool !== "select" && frame === 0 && tool !== "player") return;
              select({ kind: "player", id: p.id });
              startDrag(e, { kind: "player", id: p.id });
            }}
            className={cn("outline-none", interactive && "cursor-grab")}
          >
            <PlayerShape player={p} at={at} gkLabel={t("gkShort")} />
            {isSelected("player", p.id) ? <SelectionRing at={at} /> : null}
          </g>
        );
      })}
      {snapshot.ball ? (
        <g
          tabIndex={focusable}
          role="button"
          aria-label={t("a11y.ball", { x: fmt(snapshot.ball[0]), y: fmt(snapshot.ball[1]) })}
          aria-pressed={isSelected("ball")}
          data-element="ball"
          onFocus={() => select({ kind: "ball" })}
          onKeyDown={onElementKey}
          onPointerDown={(e) => {
            select({ kind: "ball" });
            startDrag(e, { kind: "ball" });
          }}
          className={cn("outline-none", interactive && "cursor-grab")}
        >
          <BallShape at={snapshot.ball} />
          {isSelected("ball") ? <SelectionRing at={snapshot.ball} r={1} /> : null}
        </g>
      ) : null}
      {selected?.kind === "line" && frame === 0 && interactive ? (
        <LineHandles
          line={diagram.lines.find((l) => l.id === selected.id)!}
          onStart={(e, kind) => startDrag(e, { kind, id: selected.id })}
        />
      ) : null}
      {drag?.kind === "draw" ? <DrawPreview drag={drag} /> : null}
    </svg>
  );

  const selectedPlayer =
    selected?.kind === "player" ? diagram.players.find((p) => p.id === selected.id) : undefined;
  const selectedLine =
    selected?.kind === "line" ? diagram.lines.find((l) => l.id === selected.id) : undefined;
  const selectedZone =
    selected?.kind === "zone" ? diagram.zones.find((z) => z.id === selected.id) : undefined;

  return (
    <div onKeyDown={onEditorKey} className="flex flex-col gap-4" data-testid="routine-editor">
      {editable ? (
        <Toolbar
          tool={tool}
          team={team}
          role={role}
          grid={grid}
          frame={frame}
          canUndo={canUndo}
          canRedo={canRedo}
          canDelete={!!selected && frame === 0}
          disabled={playing}
          onTool={(x) => setUi({ tool: x })}
          onTeam={(x) => {
            const first = ROLES[x].find((r) => r.id !== "gk") ?? ROLES[x][0]!;
            setUi({ team: x, role: first.id, tool: "player" });
          }}
          onRole={(x) => setUi({ role: x, tool: "player" })}
          onGrid={() => setUi({ grid: !grid })}
          onMirror={() => apply(mirror)}
          onUndo={undo}
          onRedo={redo}
          onDelete={() => selected && apply((d) => removeSelection(d, selected), null)}
          onBall={() =>
            apply((d) => setBall(d, d.diagram.ball ?? [104.5, d.side === "left" ? 67.5 : 0.5]), {
              kind: "ball",
            })
          }
          hasBall={!!diagram.ball}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-3">
          {board}
          <p id="routine-board-help" className="text-xs text-ink-3">
            {editable ? t("board.help") : t("board.helpReadOnly")}
          </p>
          <FrameStrip
            count={diagram.frames.length}
            frame={frame}
            playing={playing}
            editable={editable}
            duration={frame > 0 ? (diagram.frames[frame - 1]?.duration_ms ?? 1000) : null}
            onSelect={(i) => setUi({ frame: i, tool: i > 0 ? "select" : tool })}
            onAdd={() => {
              let index: number | null = null;
              apply((d) => {
                const r = addFrame(d);
                index = r.index;
                return r.doc;
              });
              if (index !== null) setUi({ frame: index, tool: "select" });
            }}
            onRemove={() => {
              apply((d) => removeFrame(d, frame));
              setUi({ frame: frame - 1 });
            }}
            onDuration={(ms) => apply((d) => setFrameDuration(d, frame, ms))}
            onPlay={() => setPlayT(playing || diagram.frames.length === 0 ? null : 0)}
          />
        </div>

        <aside className="flex flex-col gap-4">
          {editable ? (
            <SaveBox
              dirty={dirty}
              pending={pending}
              version={base}
              message={message}
              onMessage={setMessage}
              onSave={() => save(base)}
              notice={notice}
              onOverwrite={(v) => save(v)}
              onReload={() => window.location.reload()}
            />
          ) : null}
          <ExportBox dirty={editable && dirty} exportBase={exportBase} />
          {editable && interactive ? (
            <PropertiesPanel
              key={
                selected ? `${selected.kind}-${"id" in selected ? selected.id : "ball"}` : "none"
              }
              frame={frame}
              player={selectedPlayer}
              line={selectedLine}
              zone={selectedZone}
              ballSelected={selected?.kind === "ball"}
              players={diagram.players}
              onPlayer={(id, changes) => apply((d) => updatePlayer(d, id, changes))}
              onLine={(id, changes) => apply((d) => updateLine(d, id, changes))}
              onZone={(id, label) => apply((d) => updateZone(d, id, label))}
            />
          ) : null}
          <DetailsPanel doc={doc} editable={editable} apply={apply} />
        </aside>
      </div>
    </div>
  );
}

// --- Tahta yardımcıları ---------------------------------------------------------------------

function GridLines() {
  const lines = [];
  for (let sx = 0; sx <= 68; sx += 5)
    lines.push(<line key={`v${sx}`} x1={sx} y1={0} x2={sx} y2={52.5} />);
  for (let sy = 0; sy <= 52.5; sy += 5)
    lines.push(<line key={`h${sy}`} x1={0} y1={sy} x2={68} y2={sy} />);
  return (
    <g aria-hidden="true" stroke="var(--board-line)" strokeOpacity={0.15} strokeWidth={0.08}>
      {lines}
    </g>
  );
}

function SelectionRing({ at, r = PLAYER_RADIUS + 0.6 }: { at: Point; r?: number }) {
  const [cx, cy] = toSvg(at);
  return <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--accent)" strokeWidth={0.35} />;
}

function SelectionBox({ zone }: { zone: { x: number; y: number; w: number; h: number } }) {
  const [sx, sy] = toSvg([zone.x + zone.w, zone.y + zone.h]);
  return (
    <rect
      x={sx - 0.3}
      y={sy - 0.3}
      width={zone.h + 0.6}
      height={zone.w + 0.6}
      fill="none"
      stroke="var(--accent)"
      strokeWidth={0.3}
      strokeDasharray="0.8 0.5"
    />
  );
}

function LineHandles({
  line,
  onStart,
}: {
  line: DiagramLine;
  onStart: (e: ReactPointerEvent, kind: "from" | "to" | "curve") => void;
}) {
  const [fx, fy] = toSvg(line.from);
  const [tx, ty] = toSvg(line.to);
  const [mx, my] = toSvg(pointOnCurve(line.from, line.to, line.curve, 0.5));
  const handle = "fill-[var(--surface)] stroke-[var(--accent)] cursor-move";
  return (
    <g aria-hidden="true" data-testid="line-handles">
      <circle
        cx={fx}
        cy={fy}
        r={0.9}
        strokeWidth={0.3}
        className={handle}
        onPointerDown={(e) => onStart(e, "from")}
      />
      <circle
        cx={tx}
        cy={ty}
        r={0.9}
        strokeWidth={0.3}
        className={handle}
        onPointerDown={(e) => onStart(e, "to")}
      />
      <rect
        x={mx - 0.8}
        y={my - 0.8}
        width={1.6}
        height={1.6}
        strokeWidth={0.3}
        className={handle}
        onPointerDown={(e) => onStart(e, "curve")}
        data-testid="curve-handle"
      />
    </g>
  );
}

function DrawPreview({ drag }: { drag: Extract<Drag, { kind: "draw" }> }) {
  if (drag.tool === "zone") {
    const [ax, ay] = toSvg(drag.start);
    const [bx, by] = toSvg(drag.end);
    return (
      <rect
        x={Math.min(ax, bx)}
        y={Math.min(ay, by)}
        width={Math.abs(bx - ax)}
        height={Math.abs(by - ay)}
        fill="var(--accent)"
        fillOpacity={0.15}
        stroke="var(--accent)"
        strokeWidth={0.2}
        strokeDasharray="0.6 0.4"
      />
    );
  }
  return (
    <g opacity={0.7}>
      <LineShape
        line={{ id: "preview", kind: drag.tool, from: drag.start, to: drag.end, curve: 0 }}
      />
    </g>
  );
}

// --- Paneller ---------------------------------------------------------------------------------

function Toolbar(props: {
  tool: Tool;
  team: DiagramTeam;
  role: string;
  grid: boolean;
  frame: number;
  canUndo: boolean;
  canRedo: boolean;
  canDelete: boolean;
  disabled: boolean;
  hasBall: boolean;
  onTool: (t: Tool) => void;
  onTeam: (t: DiagramTeam) => void;
  onRole: (r: string) => void;
  onGrid: () => void;
  onMirror: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onDelete: () => void;
  onBall: () => void;
}) {
  const t = useTranslations("routines");
  const locale = useLocale();
  const baseFrame = props.frame === 0 && !props.disabled;
  return (
    <div
      role="toolbar"
      aria-label={t("toolbar.label")}
      className="flex flex-wrap items-center gap-2"
      data-testid="routine-toolbar"
    >
      <div className="flex flex-wrap gap-1" role="group" aria-label={t("toolbar.tools")}>
        {TOOLS.map(({ tool, key }) => (
          <button
            key={tool}
            type="button"
            className={btnToggle(props.tool === tool)}
            aria-pressed={props.tool === tool}
            aria-keyshortcuts={key.toUpperCase()}
            disabled={props.disabled || (tool !== "select" && props.frame > 0)}
            onClick={() => props.onTool(tool)}
            data-tool={tool}
          >
            {t(`tool.${tool}`)}
            <kbd className="hidden text-xs opacity-70 md:inline">{key.toUpperCase()}</kbd>
          </button>
        ))}
      </div>
      <div
        className="flex flex-wrap items-center gap-1"
        role="group"
        aria-label={t("toolbar.newPlayer")}
      >
        <label className="sr-only" htmlFor="routine-team">
          {t("fields.team")}
        </label>
        <select
          id="routine-team"
          className="min-h-11 rounded-md border border-line bg-surface px-2 text-sm"
          value={props.team}
          disabled={!baseFrame}
          onChange={(e) => props.onTeam(e.target.value as DiagramTeam)}
        >
          <option value="own">{t("team.own")}</option>
          <option value="opponent">{t("team.opponent")}</option>
        </select>
        <label className="sr-only" htmlFor="routine-role">
          {t("fields.role")}
        </label>
        <select
          id="routine-role"
          className="min-h-11 max-w-48 rounded-md border border-line bg-surface px-2 text-sm"
          value={props.role}
          disabled={!baseFrame}
          onChange={(e) => props.onRole(e.target.value)}
        >
          {ROLES[props.team].map((r) => (
            <option key={r.id} value={r.id}>
              {roleLabel(props.team, r.id, locale)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={btn}
          onClick={props.onBall}
          disabled={!baseFrame || props.hasBall}
        >
          {t("toolbar.ball")}
        </button>
      </div>
      <div className="flex flex-wrap gap-1" role="group" aria-label={t("toolbar.layout")}>
        <button
          type="button"
          className={btnToggle(props.grid)}
          aria-pressed={props.grid}
          aria-keyshortcuts="G"
          onClick={props.onGrid}
          disabled={props.disabled}
        >
          {t("toolbar.grid")}
        </button>
        <button
          type="button"
          className={btn}
          aria-keyshortcuts="M"
          onClick={props.onMirror}
          disabled={!baseFrame}
          data-testid="mirror"
        >
          {t("toolbar.mirror")}
        </button>
      </div>
      <div className="flex flex-wrap gap-1" role="group" aria-label={t("toolbar.history")}>
        <button
          type="button"
          className={btn}
          aria-keyshortcuts="Control+Z"
          onClick={props.onUndo}
          disabled={!props.canUndo || props.disabled}
          data-testid="undo"
        >
          {t("toolbar.undo")}
        </button>
        <button
          type="button"
          className={btn}
          aria-keyshortcuts="Control+Shift+Z"
          onClick={props.onRedo}
          disabled={!props.canRedo || props.disabled}
          data-testid="redo"
        >
          {t("toolbar.redo")}
        </button>
        <button
          type="button"
          className={btn}
          aria-keyshortcuts="Delete"
          onClick={props.onDelete}
          disabled={!props.canDelete || props.disabled}
        >
          {t("toolbar.delete")}
        </button>
      </div>
    </div>
  );
}

function FrameStrip(props: {
  count: number;
  frame: number;
  playing: boolean;
  editable: boolean;
  duration: number | null;
  onSelect: (i: number) => void;
  onAdd: () => void;
  onRemove: () => void;
  onDuration: (ms: number) => void;
  onPlay: () => void;
}) {
  const t = useTranslations("routines");
  const frames = Array.from({ length: props.count + 1 }, (_, i) => i);
  return (
    <section
      aria-labelledby="frames-title"
      className="rounded-lg border border-line bg-surface p-3"
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="frames-title" className="font-condensed text-base font-semibold">
          {t("frames.title")}
        </h2>
        <button
          type="button"
          className={btn}
          onClick={props.onPlay}
          disabled={props.count === 0}
          data-testid="play"
        >
          {props.playing ? t("frames.stop") : t("frames.play")}
        </button>
      </div>
      <div
        className="flex flex-wrap items-center gap-1"
        role="group"
        aria-label={t("frames.title")}
      >
        {frames.map((i) => (
          <button
            key={i}
            type="button"
            aria-pressed={props.frame === i}
            className={cn(btnToggle(props.frame === i), "min-w-11")}
            onClick={() => props.onSelect(i)}
            disabled={props.playing}
            data-frame={i}
          >
            {i === 0 ? t("frames.start") : t("frames.frame", { n: i })}
          </button>
        ))}
        {props.editable ? (
          <button
            type="button"
            className={btn}
            onClick={props.onAdd}
            disabled={props.playing}
            data-testid="add-frame"
          >
            {t("frames.add")}
          </button>
        ) : null}
      </div>
      {props.editable && props.frame > 0 ? (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            {t("frames.duration")}
            <input
              type="number"
              min={0.2}
              max={10}
              step={0.1}
              className="min-h-11 w-24 rounded-md border border-line bg-surface px-2 text-sm text-ink"
              key={`${props.frame}-${props.duration}`}
              defaultValue={(props.duration ?? 1000) / 1000}
              onBlur={(e) => props.onDuration(Number(e.target.value) * 1000)}
            />
          </label>
          <button type="button" className={btn} onClick={props.onRemove}>
            {t("frames.remove")}
          </button>
        </div>
      ) : null}
      <p className="mt-2 text-xs text-ink-3">
        {props.frame > 0
          ? t("frames.helpFrame")
          : props.editable
            ? t("frames.help")
            : t("frames.helpReadOnly")}
      </p>
    </section>
  );
}

function SaveBox(props: {
  dirty: boolean;
  pending: boolean;
  version: number;
  message: string;
  onMessage: (m: string) => void;
  onSave: () => void;
  notice:
    | { kind: "saved"; version: number }
    | { kind: "conflict"; current: number | null }
    | { kind: "error"; code: string }
    | null;
  onOverwrite: (base: number) => void;
  onReload: () => void;
}) {
  const t = useTranslations("routines");
  return (
    <section aria-labelledby="save-title" className="rounded-lg border border-line bg-surface p-3">
      <h2 id="save-title" className="mb-1 font-condensed text-base font-semibold">
        {t("save.title")}
      </h2>
      <p className="mb-2 text-sm text-ink-2" data-testid="save-state" aria-live="polite">
        {props.pending
          ? t("save.saving")
          : props.dirty
            ? t("save.dirty", { version: props.version })
            : t("save.clean", { version: props.version })}
      </p>
      <label className="mb-2 flex flex-col gap-1 text-xs text-ink-2">
        {t("save.message")}
        <input
          type="text"
          maxLength={200}
          value={props.message}
          onChange={(e) => props.onMessage(e.target.value)}
          className="min-h-11 rounded-md border border-line bg-surface px-2 text-sm text-ink"
          placeholder={t("save.messagePlaceholder")}
        />
      </label>
      <button
        type="button"
        className={cn(btnPrimary, "w-full")}
        onClick={props.onSave}
        disabled={!props.dirty || props.pending}
        aria-keyshortcuts="Control+S"
        data-testid="save"
      >
        {t("save.button")}
      </button>
      {props.notice?.kind === "saved" ? (
        <p role="status" className="mt-2 text-sm text-pos">
          {t("save.saved", { version: props.notice.version })}
        </p>
      ) : null}
      {props.notice?.kind === "error" ? (
        <p role="alert" className="mt-2 text-sm text-neg">
          {t("save.error", { code: props.notice.code })}
        </p>
      ) : null}
      {props.notice?.kind === "conflict" ? (
        <div role="alert" className="mt-2 flex flex-col gap-2 text-sm">
          <p className="text-neg">{t("save.conflict", { version: props.notice.current ?? "?" })}</p>
          <button type="button" className={btn} onClick={props.onReload}>
            {t("save.reload")}
          </button>
          {props.notice.current ? (
            <button
              type="button"
              className={btn}
              onClick={() =>
                props.onOverwrite(
                  props.notice!.kind === "conflict"
                    ? (props.notice as { current: number }).current
                    : props.version,
                )
              }
            >
              {t("save.overwrite")}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function ExportBox({ dirty, exportBase }: { dirty: boolean; exportBase: string }) {
  const locale = useLocale();
  const exportHref = (format: "pdf" | "png") =>
    `${exportBase}?format=${format}&lang=${locale === "en" ? "en" : "tr"}`;
  const t = useTranslations("routines");
  const link = cn(btn, "flex-1", dirty && "pointer-events-none opacity-50");
  return (
    <section
      aria-labelledby="export-title"
      className="rounded-lg border border-line bg-surface p-3"
    >
      <h2 id="export-title" className="mb-2 font-condensed text-base font-semibold">
        {t("export.title")}
      </h2>
      <div className="flex gap-2">
        <a
          href={exportHref("pdf")}
          className={link}
          aria-disabled={dirty}
          download
          data-testid="export-pdf"
        >
          PDF
        </a>
        <a
          href={exportHref("png")}
          className={link}
          aria-disabled={dirty}
          download
          data-testid="export-png"
        >
          PNG
        </a>
      </div>
      <p className="mt-2 text-xs text-ink-3">{dirty ? t("export.saveFirst") : t("export.help")}</p>
    </section>
  );
}

function PropertiesPanel(props: {
  frame: number;
  player?: DiagramPlayer;
  line?: DiagramLine;
  zone?: { id: string; label?: string | null };
  ballSelected: boolean;
  players: DiagramPlayer[];
  onPlayer: (
    id: string,
    changes: Partial<Pick<DiagramPlayer, "team" | "role" | "number" | "label">>,
  ) => void;
  onLine: (id: string, changes: Partial<Pick<DiagramLine, "kind" | "curve" | "player_id">>) => void;
  onZone: (id: string, label: string | null) => void;
}) {
  const t = useTranslations("routines");
  const locale = useLocale();
  const input = "min-h-11 rounded-md border border-line bg-surface px-2 text-sm text-ink";
  const field = "flex flex-col gap-1 text-xs text-ink-2";
  const { player, line, zone } = props;
  return (
    <section
      aria-labelledby="props-title"
      className="rounded-lg border border-line bg-surface p-3"
      data-testid="properties"
    >
      <h2 id="props-title" className="mb-2 font-condensed text-base font-semibold">
        {t("properties.title")}
      </h2>
      {player ? (
        <div className="flex flex-col gap-3">
          <label className={field}>
            {t("fields.team")}
            <select
              className={input}
              value={player.team}
              onChange={(e) => {
                const team = e.target.value as DiagramTeam;
                const role = ROLES[team].some((r) => r.id === player.role)
                  ? player.role
                  : ROLES[team][0]!.id;
                props.onPlayer(player.id, {
                  team,
                  role,
                  number: team === "own" ? (player.number ?? null) : null,
                });
              }}
              disabled={props.frame > 0}
            >
              <option value="own">{t("team.own")}</option>
              <option value="opponent">{t("team.opponent")}</option>
            </select>
          </label>
          <label className={field}>
            {t("fields.role")}
            <select
              className={input}
              value={player.role}
              onChange={(e) => props.onPlayer(player.id, { role: e.target.value })}
              disabled={props.frame > 0}
              data-testid="player-role"
            >
              {ROLES[player.team].some((r) => r.id === player.role) ? null : (
                <option value={player.role}>{player.role}</option>
              )}
              {ROLES[player.team].map((r) => (
                <option key={r.id} value={r.id}>
                  {roleLabel(player.team, r.id, locale)}
                </option>
              ))}
            </select>
          </label>
          {player.team === "own" ? (
            <label className={field}>
              {t("fields.number")}
              <input
                type="number"
                min={1}
                max={99}
                className={input}
                defaultValue={player.number ?? ""}
                disabled={props.frame > 0}
                onBlur={(e) => {
                  const n =
                    e.target.value === ""
                      ? null
                      : Math.min(99, Math.max(1, Math.round(Number(e.target.value))));
                  if (n !== (player.number ?? null)) props.onPlayer(player.id, { number: n });
                }}
              />
            </label>
          ) : null}
          <label className={field}>
            {t("fields.label")}
            <input
              type="text"
              maxLength={40}
              className={input}
              defaultValue={player.label ?? ""}
              placeholder={t("fields.labelPlaceholder")}
              disabled={props.frame > 0}
              data-testid="player-label"
              onBlur={(e) => {
                const v = e.target.value.trim() || null;
                if (v !== (player.label ?? null)) props.onPlayer(player.id, { label: v });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
            />
          </label>
        </div>
      ) : line ? (
        <div className="flex flex-col gap-3">
          <label className={field}>
            {t("fields.lineKind")}
            <select
              className={input}
              value={line.kind}
              onChange={(e) => props.onLine(line.id, { kind: e.target.value as LineKind })}
            >
              {LINE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`lineKind.${k}`)}
                </option>
              ))}
            </select>
          </label>
          <label className={field}>
            {t("fields.curve", { value: line.curve.toFixed(2) })}
            <input
              type="range"
              min={-0.6}
              max={0.6}
              step={0.02}
              value={line.curve}
              className="min-h-11 accent-[var(--pri)]"
              onChange={(e) => props.onLine(line.id, { curve: Number(e.target.value) })}
              data-testid="curve"
            />
          </label>
          <label className={field}>
            {t("fields.owner")}
            <select
              className={input}
              value={line.player_id ?? ""}
              onChange={(e) => props.onLine(line.id, { player_id: e.target.value || null })}
            >
              <option value="">{t("fields.noOwner")}</option>
              {props.players
                .filter((p) => p.team === "own")
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.number ?? "·"} · {roleLabel(p.team, p.role, locale)}
                  </option>
                ))}
            </select>
          </label>
        </div>
      ) : zone ? (
        <label className={field}>
          {t("fields.zoneLabel")}
          <select
            className={input}
            value={zone.label ?? ""}
            onChange={(e) => props.onZone(zone.id, e.target.value || null)}
          >
            <option value="">{t("fields.noLabel")}</option>
            {ZONE_CODES.map((c) => (
              <option key={c} value={c}>
                {c} · {t(`zones.${c}`)}
              </option>
            ))}
          </select>
        </label>
      ) : props.ballSelected ? (
        <p className="text-sm text-ink-2">{t("properties.ball")}</p>
      ) : (
        <p className="text-sm text-ink-2">{t("properties.empty")}</p>
      )}
    </section>
  );
}

function DetailsPanel({
  doc,
  editable,
  apply,
}: {
  doc: EditorDoc;
  editable: boolean;
  apply: (fn: (doc: EditorDoc) => EditorDoc) => void;
}) {
  const t = useTranslations("routines");
  const input = "rounded-md border border-line bg-surface px-2 py-2 text-sm text-ink";
  const field = "flex flex-col gap-1 text-xs text-ink-2";
  if (!editable) {
    return (
      <section
        aria-labelledby="details-title"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <h2 id="details-title" className="mb-2 font-condensed text-base font-semibold">
          {t("details.title")}
        </h2>
        <h3 className="text-xs font-semibold text-ink-2">{t("fields.whenToUse")}</h3>
        <p className="mb-3 whitespace-pre-line text-sm">{doc.whenToUse || "—"}</p>
        <h3 className="text-xs font-semibold text-ink-2">{t("fields.notes")}</h3>
        <p className="whitespace-pre-line text-sm">{doc.notes || "—"}</p>
      </section>
    );
  }
  return (
    <section
      aria-labelledby="details-title"
      className="rounded-lg border border-line bg-surface p-3"
    >
      <h2 id="details-title" className="mb-2 font-condensed text-base font-semibold">
        {t("details.title")}
      </h2>
      <div className="flex flex-col gap-3">
        <label className={field}>
          {t("fields.name")}
          <input
            type="text"
            maxLength={120}
            required
            className={cn(input, "min-h-11")}
            key={`name-${doc.name}`}
            defaultValue={doc.name}
            data-testid="routine-name"
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (v && v !== doc.name) apply((d) => ({ ...d, name: v }));
              else e.target.value = doc.name;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            }}
          />
        </label>
        <p className="text-xs text-ink-2">
          {t("fields.side")}:{" "}
          <span className="text-ink">{doc.side ? t(`side.${doc.side}`) : "—"}</span>
        </p>
        <label className={field}>
          {t("fields.whenToUse")}
          <textarea
            rows={3}
            maxLength={4000}
            className={input}
            key={`when-${doc.whenToUse}`}
            defaultValue={doc.whenToUse}
            onBlur={(e) =>
              e.target.value !== doc.whenToUse &&
              apply((d) => ({ ...d, whenToUse: e.target.value }))
            }
          />
        </label>
        <label className={field}>
          {t("fields.notes")}
          <textarea
            rows={5}
            maxLength={4000}
            className={input}
            key={`notes-${doc.notes}`}
            defaultValue={doc.notes}
            onBlur={(e) =>
              e.target.value !== doc.notes && apply((d) => ({ ...d, notes: e.target.value }))
            }
          />
        </label>
      </div>
    </section>
  );
}
