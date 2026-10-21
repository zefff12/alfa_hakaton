import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ALFIK, ErrorBox, Field } from "../components/ui";

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
          <div className="row" style={{ marginBottom: 32 }}>
            <div className="brand-mark" style={{ background: "#fff", color: "var(--red)" }}>А</div>
            <b style={{ fontSize: 18 }}>Умный кредитный кабинет</b>
          </div>
          <h1>Кредит для бизнеса — понятно, быстро и с помощником</h1>
          <p>Альфик подберёт продукт под вашу задачу, оценит шансы до подачи, заполнит реквизиты из ЕГРЮЛ и расскажет, что происходит с заявкой на каждом этапе.</p>
        </div>
        <img src={ALFIK.wave} alt="Альфик" className="bob" />
      </div>
      <div className="login-right">
        <div className="pill-tabs" style={{ marginBottom: 22 }}>
          <button className={mode === "demo" ? "on" : ""} onClick={() => setMode("demo")}>Демо-доступ</button>
          <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Вход</button>
          <button className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>Новый клиент</button>
        </div>
        <ErrorBox error={error} />

        {mode === "demo" && (
          <div className="stack">
            <h2>Выберите сценарий</h2>
            <p className="muted">Тестовые компании с синтетическими данными — каждая показывает свой путь заявки. Пароль у всех: <b>demo</b></p>
            {demos.map((d) => (
              <button key={d.login} className="persona" disabled={busy} onClick={() => go(() => login(d.login, d.password))}>
                <div className="avatar" style={{ background: d.role === "underwriter" ? "var(--ink)" : "var(--red)" }}>
                  {d.role === "underwriter" ? "🏦" : d.full_name[0]}
                </div>
                <div>
                  <b>{d.company ?? "Сотрудник банка"}</b> <span className="muted small">· {d.full_name} · {d.login}</span>
                  <small>{d.hint}</small>
                </div>
                <span className="badge neutral">Войти →</span>
              </button>
            ))}
            {demos.length === 0 && <p className="muted">Загружаю тестовые учётные записи…</p>}
          </div>
        )}

        {mode === "login" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); go(() => login(form.login, form.password)); }}>
            <h2>Вход в кабинет</h2>
            <Field label="Логин"><input className="input" value={form.login} onChange={set("login")} autoComplete="username" /></Field>
            <Field label="Пароль"><input className="input" type="password" value={form.password} onChange={set("password")} autoComplete="current-password" /></Field>
            <button className="btn primary" disabled={busy}>Войти</button>
          </form>
        )}

        {mode === "register" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); go(() => register(form)); }}>
            <h2>Регистрация бизнеса</h2>
            <p className="muted">Введите ИНН — Альфик сам подтянет название, ОКВЭД и адрес из ЕГРЮЛ (в демо — из симулятора). Подойдёт любой корректный по длине ИНН.</p>
            <Field label="ИНН компании или ИП" hint="10 цифр для ООО, 12 — для ИП">
              <input className="input" value={form.inn} onChange={set("inn")} inputMode="numeric" maxLength={12} placeholder="7712345678" />
            </Field>
            <Field label="ФИО"><input className="input" value={form.full_name} onChange={set("full_name")} placeholder="Иван Иванов" /></Field>
            <Field label="Должность"><input className="input" value={form.position} onChange={set("position")} placeholder="Генеральный директор" /></Field>
            <Field label="Логин" hint="латиница и цифры"><input className="input" value={form.login} onChange={set("login")} /></Field>
            <Field label="Пароль"><input className="input" type="password" value={form.password} onChange={set("password")} /></Field>
            <button className="btn primary" disabled={busy}>Создать кабинет</button>
          </form>
        )}
      </div>
    </div>
  );
}
