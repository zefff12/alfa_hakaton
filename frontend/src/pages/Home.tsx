import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ALFIK, StatusBadge, Track } from "../components/ui";
import { money, months } from "../format";
import type { Application } from "../types";

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [apps, setApps] = useState<Application[] | null>(null);
  const [feed, setFeed] = useState<any>(null);

  useEffect(() => {
    api<Application[]>("/api/applications").then(setApps);
    api("/api/feed").then(setFeed);
  }, []);

  const active = apps?.filter((a) => !a.is_final) ?? [];
  const first = user?.full_name.split(" ")[0];
  const greeting = active.length
    ? `${first}, по заявке ${active[0].number} сейчас этап «${active[0].status_label}». ${active[0].alfik.todo ? `От вас: ${active[0].alfik.todo.toLowerCase()}.` : "От вас ничего не нужно — я слежу за ней."}`
    : `${first}, я Альфик — ваш помощник по кредитам. Расскажите, на что нужны деньги, и я подберу подходящий продукт, посчитаю платёж и помогу с заявкой.`;

  return (
    <div className="stack lg">
      <section className="hero">
        <div>
          <span className="badge red">Альфик на связи</span>
          <h1 style={{ marginTop: 12 }}>Привет, {first}! 👋</h1>
          <p>{greeting}</p>
          <div className="row mt">
            {active.length ? (
              <Link className="btn primary" to={`/applications/${active[0].id}`}>Открыть заявку</Link>
            ) : (
              <Link className="btn primary" to="/advisor">Подобрать кредит</Link>
            )}
            <Link className="btn ghost" to="/precheck">Узнать шансы на одобрение</Link>
          </div>
        </div>
        <img src={ALFIK.wave} alt="Альфик" className="bob" />
      </section>

      <div className="grid g4">
        {[
          { to: "/advisor", e: "🧭", t: "Подобрать кредит", d: "Ответьте на 5 вопросов — подберу продукт под задачу" },
          { to: "/precheck", e: "🎯", t: "Каковы мои шансы?", d: "Оценка готовности до подачи, без запроса в БКИ" },
          { to: "/advisor?calc=1", e: "🧮", t: "Калькулятор", d: "Платёж, переплата и подбор под комфортный платёж" },
          { to: "/applications", e: "📄", t: "Мои заявки", d: "Статус, документы, решения и договоры" },
        ].map((a) => (
          <button key={a.t} className="action-tile" onClick={() => nav(a.to)}>
            <span className="emoji">{a.e}</span><b>{a.t}</b><span>{a.d}</span>
          </button>
        ))}
      </div>

      {active.map((a) => (
        <div className="card" key={a.id}>
          <div className="row between">
            <div>
              <h3>Заявка {a.number} · {a.product_name ?? "продукт не выбран"}</h3>
              <p className="muted small">{a.amount ? money(a.amount) : "сумма не указана"} · {months(a.term_months)}</p>
            </div>
            <div className="row">
              <StatusBadge status={a.status} label={a.status_label} />
              <Link className="btn dark sm" to={`/applications/${a.id}`}>{a.status === "DRAFT" ? "Продолжить" : "Подробнее"}</Link>
            </div>
          </div>
          <div className="mt"><Track steps={a.track.steps} current={a.track.current} failed={a.status === "REJECTED"} /></div>
        </div>
      ))}

      <div className="card">
        <h3>Как проходит кредит</h3>
        <div className="grid g4 mt">
          {[
            ["1", "Подбор и расчёт", "Альфик подбирает продукт и считает платёж"],
            ["2", "Заявка за 5 минут", "Реквизиты — из ЕГРЮЛ, сведения — из ФНС и БКИ"],
            ["3", "Решение онлайн", "Автоматически или специалистом; иногда — другие условия"],
            ["4", "Подпись и деньги", "Договор подписывается в кабинете, деньги — на счёт"],
          ].map(([n, t, d]) => (
            <div key={n} className="stack" style={{ gap: 4 }}>
              <span className="badge neutral" style={{ alignSelf: "flex-start" }}>Шаг {n}</span>
              <b>{t}</b><span className="muted small">{d}</span>
            </div>
          ))}
        </div>
      </div>

      {feed && (
        <div>
          <div className="row between" style={{ marginBottom: 12 }}>
            <h2>Лента Альфика</h2>
            <Link to="/feed" className="link">Вся лента →</Link>
          </div>
          <div className="grid g3">
            {feed.items.slice(0, 3).map((it: any) => (
              <div className="feed-card" key={it.id}>
                <span className="feed-kind">{({ news: "Новость", tip: "Совет", offer: "Предложение", guide: "Гид" } as any)[it.kind]}</span>
                <b>{it.title}</b>
                <p className="small muted">{it.body.slice(0, 140)}…</p>
                <div className="why">💡 {it.why}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
