export const money = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v)
    ? "—"
    : new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: digits }).format(v);

export const num = (v: number | null | undefined) => (v == null ? "" : new Intl.NumberFormat("ru-RU").format(v));

export const parseNum = (s: string) => {
  const n = Number(s.replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
};

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export const date = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" }) : "—";

export const months = (n: number | null | undefined) => {
  if (n == null) return "—";
  const m10 = n % 10, m100 = n % 100;
  const w = m10 === 1 && m100 !== 11 ? "месяц" : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? "месяца" : "месяцев";
  return `${n} ${w}`;
};

export const STATUS_TONE: Record<string, string> = {
  DRAFT: "neutral", SUBMITTED: "info", DATA_CHECK: "info", ENRICHMENT: "info", SCORING: "info",
  MANUAL_REVIEW: "warn", INFO_REQUESTED: "warn", APPROVED: "ok", COUNTER_OFFER: "ok", REJECTED: "bad",
  SIGNING: "ok", ISSUING: "info", DISBURSED: "ok", CANCELLED: "neutral",
};
