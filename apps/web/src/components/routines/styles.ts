/** Rutin ekranlarının ortak düğme sınıfları (dokunma hedefi en az 44 px, SPEC §13.3). */
const base =
  "inline-flex min-h-11 items-center justify-center gap-1 rounded-md border px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50";
export const btn = `${base} border-line bg-surface text-ink hover:border-pri`;
export const btnPrimary = `${base} border-pri bg-pri text-pri-ink`;
/** Seçili / seçili değil durumlu düğme (araçlar, sekmeler, filtreler). */
export function btnToggle(on: boolean): string {
  return on ? btnPrimary : btn;
}
export const inputCls = "min-h-11 rounded-md border border-line bg-surface px-2 text-sm text-ink";
