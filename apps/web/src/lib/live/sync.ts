import type { LiveDb, LocalTag } from "./db";
import type { TagPayload } from "./model";

/**
 * Çevrimdışı öncelikli senkronizasyon (ADR-0004, A-56, A-57).
 *
 * - Yazma önce IndexedDB'ye gider (`pending = 1`); ağ beklenmez.
 * - `syncOnce`: oturumu açar, bekleyenleri toplu gönderir (Idempotency-Key ile), sonra
 *   `since=lastSeq` ile diğer cihazların değişikliklerini çeker.
 * - Sunucu son yazan kazanır kuralını uygular; "stale" ya da "deleted" reddinde yerel kayıt
 *   sunucudaki sürümle değiştirilir (tam yeniden çekme).
 */

export interface ServerTag {
  id: string;
  device_id: string;
  client_ts: string;
  server_seq: number;
  deleted: boolean;
  payload: Record<string, unknown>;
}

export interface SyncResponse {
  server_seq: number;
  accepted: string[];
  rejected: { id: string; reason: string }[];
}

export interface Transport {
  openSession(fixtureId: string, deviceId: string): Promise<{ id: string }>;
  sync(
    sessionId: string,
    body: { device_id: string; changes: unknown[] },
    idempotencyKey: string,
  ): Promise<SyncResponse>;
  pull(sessionId: string, since: number): Promise<{ server_seq: number; tags: ServerTag[] }>;
}

export const BATCH = 500;
/** Sunucu sürümünün yerel kaydı geçersiz kıldığı ret nedenleri. */
const SUPERSEDED = new Set(["stale", "deleted"]);

function now(): string {
  return new Date().toISOString();
}

/** Son yazan kazanır: zaman, eşitse cihaz kimliği (sunucuyla aynı kural). */
export function isNewer(aTs: string, aDevice: string, bTs: string, bDevice: string): boolean {
  const a = Date.parse(aTs);
  const b = Date.parse(bTs);
  return a !== b ? a > b : aDevice > bDevice;
}

export async function addTag(
  db: LiveDb,
  fixtureId: string,
  payload: TagPayload,
  device: string,
): Promise<LocalTag> {
  const tag: LocalTag = {
    id: crypto.randomUUID(),
    fixtureId,
    payload,
    clientTs: now(),
    deviceId: device,
    deleted: false,
    pending: 1,
    serverSeq: null,
    error: null,
    createdAt: Date.now(),
  };
  await db.tags.add(tag);
  return tag;
}

export async function deleteTag(db: LiveDb, id: string, device: string): Promise<void> {
  await db.tags.update(id, { deleted: true, pending: 1, clientTs: now(), deviceId: device });
}

export async function pendingCount(db: LiveDb, fixtureId: string): Promise<number> {
  return db.tags.where({ fixtureId, pending: 1 }).count();
}

async function meta(db: LiveDb, fixtureId: string) {
  return (
    (await db.meta.get(fixtureId)) ?? { fixtureId, sessionId: null, lastSeq: 0, lastSyncAt: null }
  );
}

async function ensureSession(
  db: LiveDb,
  transport: Transport,
  fixtureId: string,
  device: string,
): Promise<string> {
  const current = await meta(db, fixtureId);
  if (current.sessionId) return current.sessionId;
  const session = await transport.openSession(fixtureId, device);
  await db.meta.put({ ...current, sessionId: session.id });
  return session.id;
}

function toChange(tag: LocalTag) {
  return tag.deleted
    ? { id: tag.id, op: "delete", client_ts: tag.clientTs }
    : { id: tag.id, op: "upsert", payload: tag.payload, client_ts: tag.clientTs };
}

async function push(
  db: LiveDb,
  transport: Transport,
  fixtureId: string,
  sessionId: string,
  device: string,
): Promise<{ pushed: number; rejected: number; resync: boolean }> {
  let pushed = 0;
  let rejected = 0;
  let resync = false;
  for (let round = 0; round < 20; round += 1) {
    const batch = await db.tags.where({ fixtureId, pending: 1 }).limit(BATCH).toArray();
    if (batch.length === 0) break;
    const result = await transport.sync(
      sessionId,
      { device_id: device, changes: batch.map(toChange) },
      crypto.randomUUID(),
    );
    const sent = new Map(batch.map((t) => [t.id, t]));
    const reasons = new Map(result.rejected.map((r) => [r.id, r.reason]));
    await db.transaction("rw", db.tags, async () => {
      for (const [id, before] of sent) {
        const row = await db.tags.get(id);
        // Gönderimden sonra yerelde yeniden değiştiyse bekler durumda kalır.
        if (!row || row.clientTs !== before.clientTs || row.deleted !== before.deleted) continue;
        const reason = reasons.get(id);
        if (reason === undefined) {
          await db.tags.update(id, { pending: 0, error: null });
          pushed += 1;
        } else {
          rejected += 1;
          if (SUPERSEDED.has(reason)) resync = true;
          await db.tags.update(id, {
            pending: 0,
            error: SUPERSEDED.has(reason) ? null : reason,
          });
        }
      }
    });
    if (batch.length < BATCH) break;
  }
  return { pushed, rejected, resync };
}

async function pull(
  db: LiveDb,
  transport: Transport,
  fixtureId: string,
  sessionId: string,
  since: number,
): Promise<number> {
  const page = await transport.pull(sessionId, since);
  let applied = 0;
  await db.transaction("rw", db.tags, db.meta, async () => {
    for (const remote of page.tags) {
      const local = await db.tags.get(remote.id);
      if (
        local?.pending === 1 &&
        isNewer(local.clientTs, local.deviceId, remote.client_ts, remote.device_id)
      ) {
        continue;
      }
      await db.tags.put({
        id: remote.id,
        fixtureId,
        payload: (remote.deleted && local ? local.payload : remote.payload) as TagPayload,
        clientTs: remote.client_ts,
        deviceId: remote.device_id,
        deleted: remote.deleted,
        pending: 0,
        serverSeq: remote.server_seq,
        error: null,
        createdAt: local?.createdAt ?? Date.parse(remote.client_ts),
      });
      applied += 1;
    }
    const current = await meta(db, fixtureId);
    await db.meta.put({
      ...current,
      sessionId,
      lastSeq: page.server_seq,
      lastSyncAt: Date.now(),
    });
  });
  return applied;
}

export interface SyncOutcome {
  pushed: number;
  pulled: number;
  rejected: number;
}

const inFlight = new Map<string, Promise<SyncOutcome>>();

/** Tek senkronizasyon turu. Aynı maç için eşzamanlı çağrılar aynı turu paylaşır. */
export function syncOnce(
  db: LiveDb,
  transport: Transport,
  fixtureId: string,
  device: string,
): Promise<SyncOutcome> {
  const running = inFlight.get(fixtureId);
  if (running) return running;
  const run = (async () => {
    const sessionId = await ensureSession(db, transport, fixtureId, device);
    const pushedResult = await push(db, transport, fixtureId, sessionId, device);
    const since = pushedResult.resync ? 0 : (await meta(db, fixtureId)).lastSeq;
    const pulled = await pull(db, transport, fixtureId, sessionId, since);
    return { pushed: pushedResult.pushed, pulled, rejected: pushedResult.rejected };
  })().finally(() => inFlight.delete(fixtureId));
  inFlight.set(fixtureId, run);
  return run;
}

/** Tarayıcıdan web sunucusundaki vekil uçlara (token tarayıcıya verilmez, ADR-0005). */
export const httpTransport: Transport = {
  async openSession(fixtureId, device) {
    return json(
      await fetch("/api/live/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_id: fixtureId, device_id: device }),
      }),
    );
  },
  async sync(sessionId, body, idempotencyKey) {
    return json(
      await fetch(`/api/live/sessions/${sessionId}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(body),
      }),
    );
  },
  async pull(sessionId, since) {
    return json(await fetch(`/api/live/sessions/${sessionId}/tags?since=${since}`));
  },
};

export class SyncHttpError extends Error {
  constructor(readonly status: number) {
    super(`sync failed with ${status}`);
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new SyncHttpError(response.status);
  return (await response.json()) as T;
}
