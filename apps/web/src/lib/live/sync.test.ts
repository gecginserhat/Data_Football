import "fake-indexeddb/auto";
import { afterEach, describe, expect, it } from "vitest";
import { openLiveDb, type LiveDb } from "./db";
import type { TagPayload } from "./model";
import {
  addTag,
  deleteTag,
  isNewer,
  pendingCount,
  syncOnce,
  type ServerTag,
  type SyncResponse,
  type Transport,
} from "./sync";

const FIXTURE = "11111111-1111-4111-8111-111111111111";
const PAYLOAD: TagPayload = {
  sp_type: "corner",
  team: "away",
  outcome: "cleared",
  period: 1,
  clock_s: 600,
};

/** API kurallarının küçük bir taklidi (ADR-0004): idempotent, son yazan ve silme kazanır. */
class FakeServer {
  seq = 0;
  tags = new Map<string, ServerTag>();
  calls = 0;
  online = true;

  transport(): Transport {
    return {
      openSession: async () => {
        this.check();
        return { id: "session-1" };
      },
      sync: async (_sid, body) => {
        this.check();
        return this.apply(body.device_id, body.changes as Change[]);
      },
      pull: async (_sid, since) => {
        this.check();
        return {
          server_seq: this.seq,
          tags: [...this.tags.values()]
            .filter((t) => t.server_seq > since)
            .sort((a, b) => a.server_seq - b.server_seq),
        };
      },
    };
  }

  private check() {
    this.calls += 1;
    if (!this.online) throw new TypeError("Failed to fetch");
  }

  private apply(device: string, changes: Change[]): SyncResponse {
    const accepted: string[] = [];
    const rejected: { id: string; reason: string }[] = [];
    for (const c of changes) {
      const old = this.tags.get(c.id);
      if (c.op === "delete") {
        if (!old?.deleted) {
          this.tags.set(c.id, {
            id: c.id,
            device_id: device,
            client_ts: c.client_ts,
            server_seq: ++this.seq,
            deleted: true,
            payload: old?.payload ?? {},
          });
        }
        accepted.push(c.id);
        continue;
      }
      if (old?.deleted) {
        rejected.push({ id: c.id, reason: "deleted" });
        continue;
      }
      if (old && !isNewer(c.client_ts, device, old.client_ts, old.device_id)) {
        if (old.client_ts === c.client_ts && old.device_id === device) accepted.push(c.id);
        else rejected.push({ id: c.id, reason: "stale" });
        continue;
      }
      this.tags.set(c.id, {
        id: c.id,
        device_id: device,
        client_ts: c.client_ts,
        server_seq: ++this.seq,
        deleted: false,
        payload: c.payload ?? {},
      });
      accepted.push(c.id);
    }
    return { server_seq: this.seq, accepted, rejected };
  }
}

interface Change {
  id: string;
  op: "upsert" | "delete";
  payload?: Record<string, unknown>;
  client_ts: string;
}

const dbs: LiveDb[] = [];
function freshDb(): LiveDb {
  const db = openLiveDb(`test-${crypto.randomUUID()}`);
  dbs.push(db);
  return db;
}

afterEach(async () => {
  for (const db of dbs.splice(0)) await db.delete();
});

describe("live sync", () => {
  it("keeps 20 offline tags and delivers them once when back online", async () => {
    const server = new FakeServer();
    const db = freshDb();
    server.online = false;
    for (let i = 0; i < 20; i += 1) {
      await addTag(db, FIXTURE, { ...PAYLOAD, clock_s: 60 * i }, "dev-a");
    }
    await expect(syncOnce(db, server.transport(), FIXTURE, "dev-a")).rejects.toThrow();
    expect(await pendingCount(db, FIXTURE)).toBe(20);

    server.online = true;
    const first = await syncOnce(db, server.transport(), FIXTURE, "dev-a");
    const second = await syncOnce(db, server.transport(), FIXTURE, "dev-a");

    expect(first.pushed).toBe(20);
    expect(second.pushed).toBe(0);
    expect(server.tags.size).toBe(20);
    expect(server.seq).toBe(20);
    expect(await pendingCount(db, FIXTURE)).toBe(0);
    expect((await db.meta.get(FIXTURE))?.lastSeq).toBe(20);
  });

  it("shares tags and deletions between two devices", async () => {
    const server = new FakeServer();
    const tablet = freshDb();
    const laptop = freshDb();
    const tag = await addTag(tablet, FIXTURE, PAYLOAD, "dev-a");
    await syncOnce(tablet, server.transport(), FIXTURE, "dev-a");

    await syncOnce(laptop, server.transport(), FIXTURE, "dev-b");
    expect((await laptop.tags.get(tag.id))?.payload.outcome).toBe("cleared");

    await deleteTag(laptop, tag.id, "dev-b");
    await syncOnce(laptop, server.transport(), FIXTURE, "dev-b");
    await syncOnce(tablet, server.transport(), FIXTURE, "dev-a");

    const seen = await tablet.tags.get(tag.id);
    expect(seen?.deleted).toBe(true);
    expect(seen?.payload.outcome).toBe("cleared");
  });

  it("replaces a stale local edit with the server version", async () => {
    const server = new FakeServer();
    const a = freshDb();
    const b = freshDb();
    const tag = await addTag(a, FIXTURE, PAYLOAD, "dev-a");
    await syncOnce(a, server.transport(), FIXTURE, "dev-a");
    await syncOnce(b, server.transport(), FIXTURE, "dev-b");

    // A eski bir zaman damgasıyla düzenler (saat geride); B daha yeni bir düzenleme gönderir.
    await a.tags.update(tag.id, {
      payload: { ...PAYLOAD, outcome: "shot_blocked" },
      clientTs: new Date(Date.parse(tag.clientTs) + 1000).toISOString(),
      pending: 1,
    });
    await b.tags.update(tag.id, {
      payload: { ...PAYLOAD, outcome: "goal" },
      clientTs: new Date(Date.parse(tag.clientTs) + 5000).toISOString(),
      pending: 1,
    });
    await syncOnce(b, server.transport(), FIXTURE, "dev-b");
    const result = await syncOnce(a, server.transport(), FIXTURE, "dev-a");

    expect(result.rejected).toBe(1);
    const local = await a.tags.get(tag.id);
    expect(local?.payload.outcome).toBe("goal");
    expect(local?.pending).toBe(0);
  });

  it("marks rejected tags with the reason instead of retrying forever", async () => {
    const server = new FakeServer();
    const db = freshDb();
    const transport = server.transport();
    const tag = await addTag(db, FIXTURE, PAYLOAD, "dev-a");
    const failing: Transport = {
      ...transport,
      sync: async () => ({
        server_seq: 0,
        accepted: [],
        rejected: [{ id: tag.id, reason: "routine-not-own" }],
      }),
    };
    await syncOnce(db, failing, FIXTURE, "dev-a");
    const row = await db.tags.get(tag.id);
    expect(row?.error).toBe("routine-not-own");
    expect(row?.pending).toBe(0);
  });

  it("keeps a tag pending when it changed while its sync was in flight", async () => {
    const server = new FakeServer();
    const db = freshDb();
    const base = server.transport();
    const tag = await addTag(db, FIXTURE, PAYLOAD, "dev-a");
    const racing: Transport = {
      ...base,
      sync: async (sid, body, key) => {
        await deleteTag(db, tag.id, "dev-a");
        return base.sync(sid, body, key);
      },
    };
    await syncOnce(db, racing, FIXTURE, "dev-a");
    expect((await db.tags.get(tag.id))?.pending).toBe(1);
    await syncOnce(db, base, FIXTURE, "dev-a");
    expect(server.tags.get(tag.id)?.deleted).toBe(true);
    expect(await pendingCount(db, FIXTURE)).toBe(0);
  });

  it("orders equal timestamps by device id", () => {
    const ts = "2026-10-10T13:00:00.000Z";
    expect(isNewer(ts, "b", ts, "a")).toBe(true);
    expect(isNewer(ts, "a", ts, "b")).toBe(false);
    expect(isNewer("2026-10-10T13:00:01Z", "a", "2026-10-10T13:00:00+00:00", "z")).toBe(true);
  });
});
