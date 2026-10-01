"use client";

import type { DiagramTeam } from "@kurgu/pitch";
import { temporal } from "zundo";
import { create } from "zustand";
import type { EditorDoc, Selection } from "@/lib/routine-editor";

/**
 * Editör durumu (ADR-0008): Zustand + zundo. Geri al / yinele yalnızca belgeyi (`doc`) izler;
 * seçim, araç, ızgara ve kare seçimi geçmişe girmez. Sürükleme tek adım sayılır: sürükleme
 * boyunca geçmiş durdurulur, bitişte başlangıç durumu tek kayıt olarak eklenir.
 */

export type Tool = "select" | "player" | "run" | "ball_path" | "screen" | "zone";

export interface EditorUi {
  selection: Selection | null;
  tool: Tool;
  team: DiagramTeam;
  role: string;
  grid: boolean;
  frame: number;
}

export interface EditorState extends EditorUi {
  doc: EditorDoc;
  apply: (fn: (doc: EditorDoc) => EditorDoc, selection?: Selection | null) => void;
  setUi: (ui: Partial<EditorUi>) => void;
  beginDrag: () => void;
  endDrag: () => void;
}

export function createEditorStore(initial: EditorDoc) {
  let dragStart: EditorDoc | null = null;
  const store = create<EditorState>()(
    temporal(
      (set, get) => ({
        doc: initial,
        selection: null,
        tool: "select",
        team: "own",
        role: "target",
        grid: false,
        frame: 0,
        apply: (fn, selection) => {
          const next = fn(get().doc);
          if (next === get().doc && selection === undefined) return;
          set(selection === undefined ? { doc: next } : { doc: next, selection });
        },
        setUi: (ui) => set(ui),
        beginDrag: () => {
          dragStart = get().doc;
          store.temporal.getState().pause();
        },
        endDrag: () => {
          const start = dragStart;
          dragStart = null;
          const end = get().doc;
          if (start && start !== end) {
            set({ doc: start });
            store.temporal.getState().resume();
            set({ doc: end });
          } else {
            store.temporal.getState().resume();
          }
        },
      }),
      {
        partialize: (state) => ({ doc: state.doc }),
        equality: (a, b) => a.doc === b.doc,
        limit: 200,
      },
    ),
  );
  return store;
}

export type EditorStore = ReturnType<typeof createEditorStore>;
