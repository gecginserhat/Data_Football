/**
 * Uygulama rotaları (SPEC §13.1). Yan menü, alt sekme ve boş sayfalar bu listeden üretilir.
 * `permission`: rotayı görmek için gereken izin (API'deki izin matrisiyle aynı ad).
 */
export type Permission =
  | "read_analysis"
  | "edit_routines"
  | "decide_recommendations"
  | "mark_plan_items"
  | "live_tagging_video"
  | "load_wellness"
  | "medical_notes"
  | "rule_settings"
  | "user_admin_audit"
  | "player_cards"
  | "edit_squad";

export type RouteKey =
  | "overview"
  | "prep"
  | "opponents"
  | "league"
  | "routines"
  | "live"
  | "video"
  | "reports"
  | "performance"
  | "me"
  | "admin"
  | "methodology";

export interface AppRoute {
  key: RouteKey;
  href: string;
  /** Birden fazla izinden biri yeterlidir; boşsa herkes görür. */
  anyOf: Permission[];
  /** Mobil alt sekmede gösterilir (en fazla 4). */
  tab?: boolean;
}

export const ROUTES: AppRoute[] = [
  { key: "overview", href: "/", anyOf: ["read_analysis"], tab: true },
  { key: "prep", href: "/prep", anyOf: ["read_analysis"], tab: true },
  { key: "opponents", href: "/opponents", anyOf: ["read_analysis"] },
  { key: "league", href: "/league", anyOf: [], tab: true },
  { key: "routines", href: "/routines", anyOf: ["edit_routines", "read_analysis"] },
  { key: "live", href: "/live", anyOf: ["live_tagging_video"], tab: true },
  { key: "video", href: "/video", anyOf: ["live_tagging_video"] },
  { key: "reports", href: "/reports", anyOf: ["read_analysis"] },
  { key: "performance", href: "/performance", anyOf: ["load_wellness"] },
  { key: "me", href: "/me", anyOf: [] },
  { key: "admin", href: "/admin", anyOf: ["user_admin_audit", "rule_settings", "edit_squad"] },
  { key: "methodology", href: "/methodology", anyOf: [] },
];

export function canSee(route: AppRoute, permissions: ReadonlySet<string>): boolean {
  return route.anyOf.length === 0 || route.anyOf.some((p) => permissions.has(p));
}

export function routeByKey(key: RouteKey): AppRoute {
  const route = ROUTES.find((r) => r.key === key);
  if (!route) throw new Error(`Unknown route ${key}`);
  return route;
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
