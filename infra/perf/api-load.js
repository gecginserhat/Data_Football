// API yük testi (SPEC §13.4, §18; A-93): 15 eşzamanlı kullanıcı, okuma uçlarında p95 ≤ 300 ms,
// hata oranı < %1. Her kullanıcı sayfa değiştirir gibi uçları gruplar halinde çağırır ve sayfalar
// arasında 1-3 sn bekler (analiz odasındaki gezinme).
// Çalıştırma: K6_TOKEN=<erişim belirteci> K6_TENANT=<kulüp id> k6 run infra/perf/api-load.js
// Belirteç bir duran top antrenörüne ait olmalıdır (docs/validation/performance.md).
import http from "k6/http";
import { check, group, sleep } from "k6";

const BASE = __ENV.K6_API_URL || "http://localhost:8000";
const headers = {
  Authorization: `Bearer ${__ENV.K6_TOKEN}`,
  "X-Kurgu-Tenant": __ENV.K6_TENANT,
};

export const options = {
  scenarios: {
    analysts: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "15s", target: 15 },
        { duration: "2m", target: 15 },
        { duration: "10s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<300"],
    "http_req_duration{group:::overview}": ["p(95)<300"],
    "http_req_duration{group:::opponent}": ["p(95)<300"],
    "http_req_duration{group:::prep}": ["p(95)<300"],
    "http_req_duration{group:::routines}": ["p(95)<300"],
  },
};

function get(path, name) {
  const res = http.get(`${BASE}/api/v1${path}`, { headers, tags: { name: name || path } });
  check(res, { "status 200": (r) => r.status === 200 });
  return res;
}

export function setup() {
  // Kulübün yaklaşan ilk maçı (hazırlık sayfası yalnız kulübün maçlarını açar).
  const fixture = get("/prep/overview").json().upcoming[0].fixture;
  const season = fixture.season.id;
  const rows = get(`/seasons/${season}/standings`).json().rows;
  const routines = get("/routines").json().items;
  return {
    season,
    fixture: fixture.id,
    team: rows[0].team.id,
    routine: routines.length ? routines[0].id : null,
  };
}

const think = () => sleep(1 + Math.random() * 2);

export default function (ids) {
  group("overview", () => {
    get("/me");
    get("/prep/overview");
    get(`/seasons/${ids.season}/standings`, "/seasons/{id}/standings");
    get(`/seasons/${ids.season}/team-metrics`, "/seasons/{id}/team-metrics");
  });
  think();
  group("opponent", () => {
    get(`/teams/${ids.team}/profile?season=${ids.season}`, "/teams/{id}/profile");
    get(`/teams/${ids.team}/set-pieces?season=${ids.season}&limit=50`, "/teams/{id}/set-pieces");
  });
  think();
  group("prep", () => {
    get("/fixtures");
    get(`/fixtures/${ids.fixture}/prep`, "/fixtures/{id}/prep");
  });
  think();
  group("routines", () => {
    get("/routines");
    if (ids.routine) get(`/routines/${ids.routine}`, "/routines/{id}");
  });
  think();
}
