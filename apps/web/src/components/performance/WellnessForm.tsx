import { getTranslations } from "next-intl/server";
import { PendingButton } from "@/components/reports/PendingButton";
import { btnPrimary, inputCls } from "@/components/routines/styles";
import { saveWellness } from "@/lib/performance-actions";

const ITEMS = ["sleep", "stress", "fatigue", "soreness"] as const;

/** Günlük iyi oluş girişi: Hooper maddeleri 1-7 (A-83). Aynı gün yeniden giriş üzerine yazar. */
export async function WellnessForm({
  players,
  today,
  returnTo,
}: {
  /** Seçilebilir oyuncular; tek oyuncuysa seçim gizlenir (oyuncunun kendi girişi). */
  players: { id: string; name: string }[];
  today: string;
  returnTo: "performance" | "me" | "player";
}) {
  const t = await getTranslations("performance.wellness");
  const only = players.length === 1 ? players[0] : null;
  return (
    <form
      action={saveWellness}
      className="grid max-w-2xl gap-3 sm:grid-cols-2"
      data-testid="wellness-form"
    >
      <input type="hidden" name="returnTo" value={returnTo} />
      {only ? (
        <input type="hidden" name="playerId" value={only.id} />
      ) : (
        <label className="flex flex-col gap-1 text-sm">
          {t("player")}
          <select name="playerId" required className={inputCls} data-testid="wellness-player">
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1 text-sm">
        {t("date")}
        <input
          type="date"
          name="date"
          required
          max={today}
          defaultValue={today}
          className={inputCls}
        />
      </label>
      {ITEMS.map((item) => (
        <label key={item} className="flex flex-col gap-1 text-sm">
          {t(`items.${item}`)}
          <select
            name={item}
            required
            defaultValue="4"
            className={inputCls}
            data-testid={`wellness-${item}`}
          >
            {[1, 2, 3, 4, 5, 6, 7].map((v) => (
              <option key={v} value={v}>
                {t("scale", { value: v })}
              </option>
            ))}
          </select>
        </label>
      ))}
      <p className="text-xs text-ink-3 sm:col-span-2">{t("help")}</p>
      <div className="sm:col-span-2">
        <PendingButton className={btnPrimary} pendingLabel={t("saving")} testId="wellness-save">
          {t("save")}
        </PendingButton>
      </div>
    </form>
  );
}
