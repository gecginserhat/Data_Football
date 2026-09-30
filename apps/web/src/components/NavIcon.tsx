import type { RouteKey } from "@/lib/routes";

const PATHS: Record<RouteKey, string> = {
  overview: "M3 12l9-8 9 8v8a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  prep: "M9 4h6v3H9zM5 6h2v15h10V6h2v16H5zM8 11h8M8 15h8",
  opponents: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm9 16-4.3-4.3",
  league: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  routines: "M4 4h16v16H4zM4 12h16M12 4v16M8 8l0 0M16 16l0 0",
  live: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 12a8 8 0 0 1 16 0",
  video: "M3 6h13v12H3zM16 10l5-3v10l-5-3",
  reports: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h6",
  performance: "M3 13h4l3-7 4 14 3-7h4",
  me: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  admin: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  methodology: "M4 5h7v15H4zM13 5h7v15h-7",
};

export function NavIcon({ name }: { name: RouteKey }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
