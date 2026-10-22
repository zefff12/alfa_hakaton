import { LANGS, lang, setLang } from "../i18n";

export default function LangSwitch({ dark }: { dark?: boolean }) {
  return (
    <div className={`lang-switch ${dark ? "dark" : ""}`} role="group" aria-label="Language / Язык / 语言">
      {LANGS.map((l) => (
        <button key={l.code} className={l.code === lang ? "on" : ""} aria-pressed={l.code === lang}
          onClick={() => setLang(l.code)}>{l.label}</button>
      ))}
    </div>
  );
}
