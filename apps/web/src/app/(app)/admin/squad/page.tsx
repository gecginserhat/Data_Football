import { DemoBadge, EmptyState } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { PendingButton } from "@/components/reports/PendingButton";
import { btn, btnPrimary, inputCls } from "@/components/routines/styles";
import { AerialValue } from "@/components/squad/AerialValue";
import { linkAccount, saveSquadPlayer } from "@/lib/squad-actions";
import {
  listPlayerAccounts,
  listSquad,
  squadAccess,
  type PlayerAccount,
  type SquadPlayer,
} from "@/lib/squad";

type Search = { error?: string; saved?: string; all?: string };

const POSITIONS = ["GK", "DEF", "MID", "FWD"] as const;

/** Kulüp kadrosu (A-79): forma, mevki, boy, hava topu oranı, sıçrama skoru ve hava kapasitesi. */
export default async function SquadPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const t = await getTranslations("squad");
  const tStates = await getTranslations("states");
  const access = await squadAccess();
  const crumb = (
    <nav aria-label={t("breadcrumb")} className="mb-2 text-xs text-ink-3">
      <Link href="/admin" className="underline-offset-2 hover:underline">
        {t("admin")}
      </Link>
    </nav>
  );
  if (!access.edit) {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const showAll = search.all === "1";
  const [squad, accounts] = await Promise.all([
    listSquad(showAll),
    access.admin ? listPlayerAccounts() : Promise.resolve(null),
  ]);
  if (squad.status !== "ok") {
    return (
      <>
        {crumb}
        <PageTitle>{t("title")}</PageTitle>
        <NotLoaded result={squad} />
      </>
    );
  }
  const playerAccounts = accounts?.status === "ok" ? accounts.data : null;
  return (
    <>
      {crumb}
      <PageTitle sub={t("subtitle")}>{t("title")}</PageTitle>
      {search.error ? (
        <p role="alert" className="mb-4 rounded-md border border-neg px-3 py-2 text-sm text-neg">
          {t.has(`errors.${search.error}`)
            ? t(`errors.${search.error}`)
            : t("errors.generic", { code: search.error })}
        </p>
      ) : null}
      {search.saved ? (
        <p role="status" className="mb-4 rounded-md border border-pos px-3 py-2 text-sm text-pos">
          {t("saved")}
        </p>
      ) : null}

      <Section
        id="squad-list"
        title={t("list")}
        action={
          <Link
            href={showAll ? "/admin/squad" : "/admin/squad?all=1"}
            className="text-sm text-pri underline-offset-2 hover:underline"
          >
            {showAll ? t("activeOnly") : t("showAll")}
          </Link>
        }
      >
        {squad.data.length === 0 ? (
          <EmptyState title={t("emptyTitle")} description={t("empty")} />
        ) : (
          <SquadTable players={squad.data} accounts={playerAccounts} />
        )}
        <p className="mt-2 text-xs text-ink-3">{t("aerialHelp")}</p>
      </Section>

      <Section id="squad-add" title={t("add")}>
        <PlayerForm />
      </Section>
    </>
  );
}

async function SquadTable({
  players,
  accounts,
}: {
  players: SquadPlayer[];
  accounts: PlayerAccount[] | null;
}) {
  const t = await getTranslations("squad");
  const format = await getFormatter();
  const pct = (v: number | null | undefined) =>
    v == null ? "—" : format.number(v, { style: "percent", maximumFractionDigits: 0 });
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-max text-left text-sm" data-testid="squad-table">
        <caption className="sr-only">{t("list")}</caption>
        <thead className="border-b border-line text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-3 py-2 text-right">
              {t("fields.shirt")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("fields.name")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("fields.position")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("fields.height")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("fields.aerial")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("fields.jump")}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t("capacity")}
            </th>
            <th scope="col" className="px-3 py-2">
              {t("account")}
            </th>
            <th scope="col" className="px-3 py-2">
              <span className="sr-only">{t("edit")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => (
            <tr
              key={p.id}
              className="border-b border-line align-top last:border-0"
              data-testid="squad-row"
              data-player={p.name}
            >
              <td className="px-3 py-2 text-right tabular-nums">{p.shirt_number ?? "—"}</td>
              <th scope="row" className="px-3 py-2 font-medium">
                <span className="flex flex-wrap items-center gap-2">
                  {p.name}
                  {p.is_demo ? <DemoBadge label={t("demo")} /> : null}
                  {!p.active ? (
                    <span className="text-xs font-normal text-ink-3">{t("inactive")}</span>
                  ) : null}
                </span>
              </th>
              <td className="px-3 py-2">{t(`positions.${p.position}`)}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {p.height_cm ? t("cm", { value: p.height_cm }) : "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(p.aerial_win_pct)}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {p.jump_score == null ? "—" : format.number(p.jump_score)}
              </td>
              <td className="px-3 py-2 text-right">
                <AerialValue score={p.aerial} />
              </td>
              <td className="px-3 py-2">
                {accounts ? (
                  <AccountSelect player={p} accounts={accounts} />
                ) : p.has_account ? (
                  t("linked")
                ) : (
                  "—"
                )}
              </td>
              <td className="px-3 py-2">
                <details>
                  <summary className="min-h-11 cursor-pointer py-2 text-pri">{t("edit")}</summary>
                  <div className="mt-2 w-[min(32rem,80vw)]">
                    <PlayerForm player={p} />
                  </div>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function AccountSelect({
  player,
  accounts,
}: {
  player: SquadPlayer;
  accounts: PlayerAccount[];
}) {
  const t = await getTranslations("squad");
  const current = accounts.find((a) => a.squad_player_id === player.id);
  return (
    <form action={linkAccount} className="flex items-center gap-2">
      <input type="hidden" name="playerId" value={player.id} />
      <label className="sr-only" htmlFor={`account-${player.id}`}>
        {t("accountFor", { name: player.name })}
      </label>
      <select
        id={`account-${player.id}`}
        name="userId"
        defaultValue={current?.user_id ?? ""}
        className={inputCls}
      >
        <option value="">{t("noAccount")}</option>
        {accounts.map((a) => (
          <option key={a.user_id} value={a.user_id}>
            {a.name ?? a.user_id}
          </option>
        ))}
      </select>
      <PendingButton className={btn} pendingLabel={t("saving")}>
        {t("link")}
      </PendingButton>
    </form>
  );
}

async function PlayerForm({ player }: { player?: SquadPlayer }) {
  const t = await getTranslations("squad");
  const id = player?.id ?? "new";
  return (
    <form
      action={saveSquadPlayer}
      className="grid gap-3 sm:grid-cols-2"
      data-testid={player ? "squad-edit-form" : "squad-add-form"}
    >
      {player ? <input type="hidden" name="id" value={player.id} /> : null}
      <label className="flex flex-col gap-1 text-sm sm:col-span-2">
        {t("fields.name")}
        <input
          name="name"
          required
          maxLength={120}
          defaultValue={player?.name}
          className={inputCls}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("fields.shirt")}
        <input
          name="shirt_number"
          type="number"
          min={1}
          max={99}
          defaultValue={player?.shirt_number ?? undefined}
          className={inputCls}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("fields.position")}
        <select
          name="position"
          required
          defaultValue={player?.position ?? "DEF"}
          className={inputCls}
        >
          {POSITIONS.map((p) => (
            <option key={p} value={p}>
              {t(`positions.${p}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("fields.heightCm")}
        <input
          name="height_cm"
          type="number"
          min={150}
          max={215}
          defaultValue={player?.height_cm ?? undefined}
          className={inputCls}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("fields.aerialPct")}
        <input
          name="aerial_win_pct"
          type="number"
          min={0}
          max={100}
          step={1}
          defaultValue={
            player?.aerial_win_pct == null ? undefined : Math.round(player.aerial_win_pct * 100)
          }
          className={inputCls}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("fields.jumpScore")}
        <input
          name="jump_score"
          type="number"
          min={0}
          max={1}
          step={0.01}
          defaultValue={player?.jump_score ?? undefined}
          className={inputCls}
        />
      </label>
      {player ? (
        <label className="flex min-h-11 items-center gap-3 text-sm">
          <input type="checkbox" name="active" defaultChecked={player.active} className="size-5" />
          {t("fields.active")}
        </label>
      ) : null}
      <div className="sm:col-span-2">
        <PendingButton
          className={btnPrimary}
          pendingLabel={t("saving")}
          testId={`squad-save-${id}`}
        >
          {player ? t("save") : t("addButton")}
        </PendingButton>
      </div>
    </form>
  );
}
