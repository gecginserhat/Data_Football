/**
 * Kural seti düzenleyicisinin saf yardımcıları (A-51). Kural JSON'u API'den gelir; burada yalnızca
 * eşik, öncelik ve açık/kapalı alanları değiştirilir. Doğrulama API'dedir.
 */

export interface RuleCondition {
  subject: string;
  metric: string;
  op: string;
  value?: number | boolean | null;
}

export type RuleJson = {
  id: string;
  area: string;
  priority: number;
  enabled?: boolean;
  scope?: string;
  title: string;
  when: unknown;
} & Record<string, unknown>;

export interface RuleEdits {
  enabled: Record<string, boolean>;
  priority: Record<string, number>;
  /** Koşul değerleri, `conditionsOf` sırasıyla. `null` değiştirilmemiş demektir. */
  values: Record<string, (number | null)[]>;
}

function isCondition(node: unknown): node is RuleCondition {
  return typeof node === "object" && node !== null && "subject" in node && "metric" in node;
}

/** `when` ağacındaki koşullar, derinlik öncelikli ve sabit sırayla. */
export function conditionsOf(when: unknown): RuleCondition[] {
  const out: RuleCondition[] = [];
  const walk = (node: unknown) => {
    if (isCondition(node)) {
      out.push(node);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    const group = node as Record<string, unknown>;
    for (const key of ["all", "any"]) {
      const items = group[key];
      if (Array.isArray(items)) items.forEach(walk);
    }
    if ("not" in group) walk(group.not);
  };
  walk(when);
  return out;
}

/** Değeri sayı olan (düzenlenebilir) koşul mu? Mantıksal değerler düzenleyicide değişmez. */
export function isEditable(condition: RuleCondition): boolean {
  return typeof condition.value === "number";
}

/** Sıra işlemlerinde eşik tam sayıdır (lig sırası). */
export function isRankOp(op: string): boolean {
  return op.startsWith("rank_");
}

/** Düzenlemeleri kuralların derin kopyasına uygular; girdi değişmez. */
export function applyEdits(rules: RuleJson[], edits: RuleEdits): RuleJson[] {
  return rules.map((rule) => {
    const copy = structuredClone(rule);
    if (rule.id in edits.enabled) copy.enabled = edits.enabled[rule.id];
    const priority = edits.priority[rule.id];
    if (priority !== undefined && Number.isInteger(priority)) copy.priority = priority;
    const values = edits.values[rule.id] ?? [];
    conditionsOf(copy.when).forEach((condition, i) => {
      const value = values[i];
      if (value !== null && value !== undefined && isEditable(condition)) {
        condition.value = value;
      }
    });
    return copy;
  });
}

function parseNumber(raw: FormDataEntryValue | null): number | null {
  if (raw === null) return null;
  const text = String(raw).trim().replace(",", ".");
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/**
 * Form alanlarından düzenlemeler. Alan adları: `enabled:<id>` (onay kutusu), `priority:<id>`,
 * `value:<id>:<i>`. Kuralın `present:<id>` alanı yoksa kural formda değildir ve değişmez.
 */
export function editsFromForm(form: FormData, rules: RuleJson[]): RuleEdits {
  const edits: RuleEdits = { enabled: {}, priority: {}, values: {} };
  for (const rule of rules) {
    if (!form.has(`present:${rule.id}`)) continue;
    edits.enabled[rule.id] = form.get(`enabled:${rule.id}`) === "on";
    const priority = parseNumber(form.get(`priority:${rule.id}`));
    if (priority !== null) edits.priority[rule.id] = priority;
    edits.values[rule.id] = conditionsOf(rule.when).map((_, i) =>
      parseNumber(form.get(`value:${rule.id}:${i}`)),
    );
  }
  return edits;
}
