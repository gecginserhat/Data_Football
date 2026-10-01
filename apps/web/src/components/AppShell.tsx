"use client";

import { cn } from "@kurgu/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { ROUTES, isActive, type RouteKey } from "@/lib/routes";
import { NavIcon } from "./NavIcon";

export interface AppShellProps {
  visible: RouteKey[];
  clubName: string | null;
  userName: string | null;
  footer: ReactNode;
  children: ReactNode;
}

/** Masaüstünde yan menü, mobilde alt sekme ve çekmece menü (SPEC §13.3). */
export function AppShell({ visible, clubName, userName, footer, children }: AppShellProps) {
  const t = useTranslations();
  const pathname = usePathname();
  // Çekmece açıldığı yolu saklar; yol değişince kendiliğinden kapanır (efekt gerekmez).
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawerOpen = drawerPath === pathname;
  const routes = ROUTES.filter((r) => visible.includes(r.key));
  const tabs = routes.filter((r) => r.tab).slice(0, 4);

  const navList = (
    <ul className="flex flex-col gap-1">
      {routes.map((route) => {
        const active = isActive(route.href, pathname);
        return (
          <li key={route.key}>
            <Link
              href={route.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm",
                active
                  ? "border-l-4 border-accent bg-white/10 font-semibold text-brand-ink"
                  : "border-l-4 border-transparent text-brand-ink/85 hover:bg-white/5",
              )}
            >
              <NavIcon name={route.key} />
              {t(`nav.${route.key}`)}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  const clubCard = (
    <div className="rounded-md bg-white/5 p-3">
      <p className="text-[11px] uppercase tracking-wide text-brand-ink/60">{t("app.yourClub")}</p>
      {clubName ? (
        <p className="mt-1 flex items-center gap-2 text-sm font-medium text-brand-ink">
          {/* Kulüp kısa kodu (TS, GS…) Faz 1'de takım kaydından gelir; şimdilik vurgu işareti. */}
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full bg-accent" />
          <span className="truncate">{clubName}</span>
        </p>
      ) : (
        <p className="mt-1 text-sm text-brand-ink/80">{t("app.noClub")}</p>
      )}
      {userName ? <p className="mt-2 truncate text-xs text-brand-ink/60">{userName}</p> : null}
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        {t("app.skipToContent")}
      </a>

      <aside className="hidden bg-brand text-brand-ink lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:gap-6 lg:p-4">
        <p className="px-3 font-condensed text-2xl font-bold">{t("app.name")}</p>
        {clubCard}
        <nav aria-label={t("app.mainNav")} className="flex-1 overflow-y-auto">
          {navList}
        </nav>
        <div>{footer}</div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-brand px-4 text-brand-ink lg:hidden">
        <p className="font-condensed text-xl font-bold">{t("app.name")}</p>
        <button
          type="button"
          onClick={() => setDrawerPath(pathname)}
          aria-expanded={drawerOpen}
          aria-controls="drawer"
          className="min-h-11 min-w-11 rounded-md px-3 text-sm"
        >
          {t("app.menu")}
        </button>
      </header>

      {drawerOpen ? (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          id="drawer"
          aria-label={t("app.menu")}
        >
          <button
            type="button"
            aria-label={t("app.closeMenu")}
            className="absolute inset-0 bg-black/40"
            onClick={() => setDrawerPath(null)}
          />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col gap-6 overflow-y-auto bg-brand p-4 text-brand-ink">
            <button
              type="button"
              onClick={() => setDrawerPath(null)}
              className="min-h-11 self-end rounded-md px-3 text-sm"
            >
              {t("app.closeMenu")}
            </button>
            {clubCard}
            <nav aria-label={t("app.mainNav")}>{navList}</nav>
            <div>{footer}</div>
          </div>
        </div>
      ) : null}

      <main id="main" className="min-w-0 px-4 pb-24 pt-6 lg:px-8 lg:pb-8">
        {children}
      </main>

      <nav
        aria-label={t("app.tabNav")}
        className="fixed inset-x-0 bottom-0 z-30 grid border-t border-line bg-surface lg:hidden"
        style={{ gridTemplateColumns: `repeat(${Math.max(tabs.length, 1)}, minmax(0, 1fr))` }}
      >
        {tabs.map((route) => {
          const active = isActive(route.href, pathname);
          return (
            <Link
              key={route.key}
              href={route.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px]",
                active ? "font-semibold text-pri" : "text-ink-3",
              )}
            >
              <NavIcon name={route.key} />
              {t(`nav.${route.key}`)}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
