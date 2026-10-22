import { LOCALE, lang, t } from "./i18n";

export const money = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v)
    ? "—"
    : new Intl.NumberFormat(LOCALE, { style: "currency", currency: "RUB", currencyDisplay: "narrowSymbol", maximumFractionDigits: digits }).format(v);

export const num = (v: number | null | undefined) => (v == null ? "" : new Intl.NumberFormat(LOCALE).format(v));

export const parseNum = (s: string) => {
  const n = Number(s.replace(/[\s,]/g, "").replace(/[^\d.]/g, ""));
  return Number.isFinite(n) ? n : 0;
};

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(LOCALE, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export const date = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString(LOCALE, { day: "2-digit", month: "long", year: "numeric" }) : "—";

export const months = (n: number | null | undefined) => {
  if (n == null) return "—";
  if (lang === "zh") return `${n} ${t("месяцев")}`;
  if (lang === "en") return `${n} ${n === 1 ? t("месяц") : t("месяцев")}`;
  const m10 = n % 10, m100 = n % 100;
  const w = m10 === 1 && m100 !== 11 ? t("месяц") : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? t("месяца") : t("месяцев");
  return `${n} ${w}`;
};

export const STATUS_TONE: Record<string, string> = {
  DRAFT: "neutral", SUBMITTED: "info", DATA_CHECK: "info", ENRICHMENT: "info", SCORING: "info",
  MANUAL_REVIEW: "warn", INFO_REQUESTED: "warn", APPROVED: "ok", COUNTER_OFFER: "ok", REJECTED: "bad",
  SIGNING: "ok", ISSUING: "info", DISBURSED: "ok", CANCELLED: "neutral",
};
