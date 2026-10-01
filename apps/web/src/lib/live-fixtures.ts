import "server-only";
import { getFixtures, getSeasons, pickSeason, type Fixture, type Loaded } from "./analysis";
import { clubTeamId } from "./live-data";

/** Kulübün güncel sezondaki maçları: oynananlar (son önce) ve sıradakiler. */
export async function clubFixtures(): Promise<
  Loaded<{ played: Fixture[]; upcoming: Fixture[] }> | { status: "no-club" }
> {
  const seasons = await getSeasons();
  if (seasons.status !== "ok") return seasons;
  const season = pickSeason(seasons.data);
  if (!season) return { status: "missing" };
  const club = await clubTeamId(season.id);
  if (!club) return { status: "no-club" };
  const [played, upcoming] = await Promise.all([
    getFixtures(club, season.id, "finished", 50),
    getFixtures(club, season.id, "scheduled", 8),
  ]);
  if (played.status !== "ok") return played;
  if (upcoming.status !== "ok") return upcoming;
  return { status: "ok", data: { played: [...played.data].reverse(), upcoming: upcoming.data } };
}
