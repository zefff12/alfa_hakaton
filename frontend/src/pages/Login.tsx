import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";
import { t } from "../i18n";
import LangSwitch from "../components/LangSwitch";

interface Demo { login: string; password: string; role: string; full_name: string; company: string | null; hint: string | null }

export default function Login() {
  const { login, register, user } = useAuth();
  const nav = useNavigate();
  const [demos, setDemos] = useState<Demo[]>([]);
  const [mode, setMode] = useState<"demo" | "login" | "register">("demo");
  const [form, setForm] = useState<Record<string, string>>({ login: "", password: "", full_name: "", inn: "", position: "" });
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<Demo[]>("/api/auth/demo-accounts").then(setDemos).catch(() => {}); }, []);
  useEffect(() => { if (user) nav(user.role === "underwriter" ? "/bank" : "/"); }, [user, nav]);

  async function go(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="login-page">
      <div className="login-left">
        <div>
          <div className="logo" style={{ padding: "0 0 32px" }}>
            <b style={{ fontSize: 30 }}>{t("Альфа Банк")}</b><i />
            <small>{t("Умный кредитный кабинет")}</small>
          </div>
          <h1>{t("Кредит для бизнеса — понятно, быстро и с помощником")}</h1>
          <p>{t("Альфик подберёт продукт под вашу задачу, оценит шансы до подачи, заполнит реквизиты из ЕГРЮЛ и расскажет, что происходит с заявкой на каждом этапе.")}</p>
        </div>
        <img src="/brand/alfik-jump.webp" alt={t("Альфик")} className="bob" />
      </div>
      <div className="login-right">
        <div className="row between" style={{ marginBottom: 22 }}>
        <div className="pill-tabs">
          <button className={mode === "demo" ? "on" : ""} onClick={() => setMode("demo")}>{t("Демо-доступ")}</button>
          <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>{t("Вход")}</button>
          <button className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>{t("Новый клиент")}</button>
        </div>
        <LangSwitch />
        </div>
        <ErrorBox error={error} />

        {mode === "demo" && (
          <div className="stack">
            <h2>{t("Выберите сценарий")}</h2>
            <p className="muted">{t("Тестовые компании с синтетическими данными — каждая показывает свой путь заявки. Пароль у всех:")} <b>demo</b></p>
            {demos.map((d) => (
              <button key={d.login} className="persona" disabled={busy} onClick={() => go(() => login(d.login, d.password))}>
                <div className="avatar" style={{ background: d.role === "underwriter" ? "var(--ink)" : "var(--red)" }}>
                  {d.role === "underwriter" ? "🏦" : d.full_name[0]}
                </div>
                <div>
                  <b>{d.company ?? t("Сотрудник банка")}</b> <span className="muted small">· {d.full_name} · {d.login}</span>
                  <small>{d.hint}</small>
                </div>
                <span className="badge neutral">{t("Войти →")}</span>
              </button>
            ))}
            {demos.length === 0 && <p className="muted">{t("Загружаю тестовые учётные записи…")}</p>}
          </div>
        )}

        {mode === "login" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); go(() => login(form.login, form.password)); }}>
            <h2>{t("Вход в кабинет")}</h2>
            <Field label={t("Логин")}><input className="input" value={form.login} onChange={set("login")} autoComplete="username" /></Field>
            <Field label={t("Пароль")}><input className="input" type="password" value={form.password} onChange={set("password")} autoComplete="current-password" /></Field>
            <button className="btn primary" disabled={busy}>{t("Войти")}</button>
          </form>
        )}

        {mode === "register" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); go(() => register(form)); }}>
            <h2>{t("Регистрация бизнеса")}</h2>
            <p className="muted">{t("Введите ИНН — Альфик сам подтянет название, ОКВЭД и адрес из ЕГРЮЛ (в демо — из симулятора). Подойдёт любой корректный по длине ИНН.")}</p>
            <Field label={t("ИНН компании или ИП")} hint={t("10 цифр для ООО, 12 — для ИП")}>
              <input className="input" value={form.inn} onChange={set("inn")} inputMode="numeric" maxLength={12} placeholder="7712345678" />
            </Field>
            <Field label={t("ФИО")}><input className="input" value={form.full_name} onChange={set("full_name")} placeholder={t("Иван Иванов")} /></Field>
            <Field label={t("Должность")}><input className="input" value={form.position} onChange={set("position")} placeholder={t("Генеральный директор")} /></Field>
            <Field label={t("Логин")} hint={t("латиница и цифры")}><input className="input" value={form.login} onChange={set("login")} /></Field>
            <Field label={t("Пароль")}><input className="input" type="password" value={form.password} onChange={set("password")} /></Field>
            <button className="btn primary" disabled={busy}>{t("Создать кабинет")}</button>
          </form>
        )}
      </div>
    </div>
  );
}
