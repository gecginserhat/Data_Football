import "server-only";
import type { Schemas } from "@kurgu/api-client";
import { cache } from "react";
import type { Loaded } from "./analysis";
import { apiClient, getMe, permissionSet } from "./api";

/**
 * Kadro, rakip hedefleri, markaj ve rol atamalarının sunucu tarafı veri katmanı (SPEC §7.3,
 * ADR-0015, A-79 … A-87). Hava skoru ve Macar algoritması API'de hesaplanır.
 */

export type SquadPlayer = Schemas["SquadPlayerOut"];
export type Target = Schemas["TargetOut"];
export type Marking = Schemas["MarkingOut"];
export type MarkingRow = Schemas["MarkingRow"];
export type Assignments = Schemas["AssignmentsOut"];
export type RoutineAssignment = Schemas["RoutineAssignmentOut"];
export type Cards = Schemas["CardsOut"];
export type TaskCard = Schemas["TaskCard"];
export type PlayerAccount = Schemas["PlayerAccountOut"];

function settle<T>(data: T | undefined, response: Response): Loaded<T> {
  if (data !== undefined) return { status: "ok", data };
  if (response.status === 403) return { status: "forbidden" };
  if (response.status === 404 || response.status === 422) return { status: "missing" };
  return { status: "error" };
}

async function guarded<T>(run: () => Promise<Loaded<T>>): Promise<Loaded<T>> {
  try {
    return await run();
  } catch {
    return { status: "error" };
  }
}

export interface SquadAccess {
  /** Kadroyu düzenleme (A-79). */
  edit: boolean;
  /** Markaj kaydı, rakip hedefleri ve rol atamaları (`decide_recommendations`). */
  decide: boolean;
  /** Oyuncu hesabı bağlama (yönetici). */
  admin: boolean;
  /** Oturumdaki oyuncu hesabının kadro kaydı. */
  playerId: string | null;
  /** Görev kartı kapsamı. */
  cards: "all" | "own" | null;
}

export async function squadAccess(): Promise<SquadAccess> {
  const me = await getMe();
  if (me.status !== "ok") {
    return { edit: false, decide: false, admin: false, playerId: null, cards: null };
  }
  const perms = permissionSet(me.me);
  const cards = me.me.active_tenant?.permissions.player_cards;
  return {
    edit: perms.has("edit_squad"),
    decide: perms.has("decide_recommendations"),
    admin: perms.has("user_admin_audit"),
    playerId: me.me.active_tenant?.squad_player_id ?? null,
    cards: cards === "all" || cards === "own" ? cards : null,
  };
}

export const listSquad = cache((includeInactive = false): Promise<Loaded<SquadPlayer[]>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/squad", {
      params: { query: { include_inactive: includeInactive } },
    });
    return settle(data, response);
  }),
);

export async function listPlayerAccounts(): Promise<Loaded<PlayerAccount[]>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/squad/accounts");
    return settle(data, response);
  });
}

export const getMarking = cache((fixtureId: string, zonal?: string): Promise<Loaded<Marking>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}/marking", {
      params: {
        path: { fixture_id: fixtureId },
        query: zonal === undefined ? {} : { zonal },
      },
    });
    return settle(data, response);
  }),
);

export const getAssignments = cache((fixtureId: string): Promise<Loaded<Assignments>> =>
  guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/fixtures/{fixture_id}/assignments", {
      params: { path: { fixture_id: fixtureId } },
    });
    return settle(data, response);
  }),
);

export async function getCards(playerId: string): Promise<Loaded<Cards>> {
  return guarded(async () => {
    const client = await apiClient();
    const { data, response } = await client.GET("/api/v1/squad/{player_id}/cards", {
      params: { path: { player_id: playerId } },
    });
    return settle(data, response);
  });
}
