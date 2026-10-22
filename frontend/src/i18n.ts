/**
 * Мультиязычность интерфейса: русский (исходный), английский, китайский.
 *
 * t("русский текст", ...args) — ключом служит сам русский текст, поэтому при
 * отсутствии перевода интерфейс показывает оригинал, а не пустую строку.
 * Язык хранится в localStorage; при смене язык применяется перезагрузкой —
 * так и тексты интерфейса, и данные с сервера (X-Lang) приходят на новом языке.
 */
import DICT from "./i18n-dict";

export type Lang = "ru" | "en" | "zh";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
  { code: "zh", label: "中文" },
];

const KEY = "alfa_credit_lang";

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "ru" || saved === "en" || saved === "zh") return saved;
  } catch {
    /* хранилище недоступно — используем язык по умолчанию */
  }
  return "ru";
}

export const lang: Lang = initial();
export const LOCALE = { ru: "ru-RU", en: "en-US", zh: "zh-CN" }[lang];
export const SPEECH_LANG = LOCALE;

if (typeof document !== "undefined") document.documentElement.lang = lang;

export function setLang(next: Lang) {
  if (next === lang) return;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* без хранилища язык применится только до перезагрузки */
  }
  window.location.reload();
}

export function t(key: string, ...args: unknown[]): string {
  let s = lang === "ru" ? key : DICT[key]?.[lang === "en" ? 0 : 1] ?? key;
  args.forEach((a, i) => { s = s.split(`{${i}}`).join(String(a)); });
  return s;
}
