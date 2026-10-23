import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { t } from "../i18n";
import { getTheme, setTheme, type Theme } from "../theme";

export default function ThemeToggle() {
  const [theme, setState] = useState<Theme>(getTheme());
  useEffect(() => {
    const sync = () => setState(getTheme());
    window.addEventListener("theme:changed", sync);
    return () => window.removeEventListener("theme:changed", sync);
  }, []);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button className="icon-btn theme-toggle" onClick={() => setTheme(next)}
      aria-label={next === "light" ? t("Светлая тема") : t("Тёмная тема")} title={next === "light" ? t("Светлая тема") : t("Тёмная тема")}>
      {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
    </button>
  );
}
