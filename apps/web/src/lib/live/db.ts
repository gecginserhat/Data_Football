import Dexie, { type EntityTable } from "dexie";
import type { TagPayload } from "./model";

/**
 * Canlı kayıtların tarayıcıdaki deposu (IndexedDB, SPEC §13.2). Her dokunuş önce buraya yazılır;
 * senkronizasyon bekleyenleri (`pending = 1`) sunucuya taşır (ADR-0004).
 */

export interface LocalTag {
  id: string;
  fixtureId: string;
  payload: TagPayload;
  /** Son yazan kazanır karşılaştırmasının zamanı (ISO). */
  clientTs: string;
  deviceId: string;
  deleted: boolean;
  /** 1: sunucuya gönderilmeyi bekliyor (IndexedDB boolean dizinlemez). */
  pending: 0 | 1;
  serverSeq: number | null;
  /** Sunucunun reddetme nedeni (ör. `routine-not-own`); kayıt yerelde kalır. */
  error: string | null;
  createdAt: number;
}

export interface LiveMeta {
  fixtureId: string;
  sessionId: string | null;
  lastSeq: number;
  lastSyncAt: number | null;
}

export type LiveDb = Dexie & {
  tags: EntityTable<LocalTag, "id">;
  meta: EntityTable<LiveMeta, "fixtureId">;
};

export function openLiveDb(name = "kurgu-live"): LiveDb {
  const db = new Dexie(name) as LiveDb;
  db.version(1).stores({
    tags: "id, fixtureId, [fixtureId+pending], createdAt",
    meta: "fixtureId",
  });
  return db;
}

let shared: LiveDb | null = null;

export function liveDb(): LiveDb {
  shared ??= openLiveDb();
  return shared;
}

const DEVICE_KEY = "kurgu-device-id";

/** Bu tarayıcının kalıcı cihaz kimliği (eşit zamanlı yazmalarda sıralama için). */
export function deviceId(): string {
  try {
    const existing = localStorage.getItem(DEVICE_KEY);
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem(DEVICE_KEY, created);
    return created;
  } catch {
    return "device-unknown";
  }
}
