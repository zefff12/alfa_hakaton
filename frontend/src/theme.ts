/**
 * Светлая и тёмная тема кабинета. Выбор хранится в браузере; тема ставится
 * атрибутом data-theme на <html> ещё до отрисовки (скрипт в index.html),
 * поэтому при загрузке страница не «мигает» другой темой.
 */
export type Theme = "dark" | "light";

const KEY = "alfa_credit_theme";

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setTheme(next: Theme) {
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* без хранилища тема действует до перезагрузки */
  }
  window.dispatchEvent(new Event("theme:changed"));
}
