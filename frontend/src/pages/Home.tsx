import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ALFIK, StatusBadge, Track } from "../components/ui";
import { money, months } from "../format";
import type { Application } from "../types";
import { t } from "../i18n";

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
    ? t("{0}, по заявке {1} сейчас этап «{2}». {3}", first, active[0].number, active[0].status_label, active[0].alfik.todo ? t("От вас: {0}.", active[0].alfik.todo.toLowerCase()) : t("От вас ничего не нужно — я слежу за ней."))
    : t("{0}, я Альфик — ваш помощник по кредитам. Расскажите, на что нужны деньги, и я подберу подходящий продукт, посчитаю платёж и помогу с заявкой.", first);

  return (
    <div className="stack lg">
      <section className="hero">
        <div>
          <span className="badge red">{t("Альфик на связи")}</span>
          <h1 style={{ marginTop: 12 }}>{t("Привет,")} {first}! 👋</h1>
          <p>{greeting}</p>
          <div className="row mt">
            {active.length ? (
              <Link className="btn primary" to={`/applications/${active[0].id}`}>{t("Открыть заявку")}</Link>
            ) : (
              <Link className="btn primary" to="/talk">{t("🎙 Рассказать Альфику")}</Link>
            )}
            <Link className="btn ghost" to="/precheck">{t("Узнать шансы на одобрение")}</Link>
          </div>
        </div>
        <img src={ALFIK.wave} alt={t("Альфик")} className="bob" />
      </section>

      <div className="grid g4">
        {[
          { to: "/talk", e: "🎙", t: t("Рассказать Альфику"), d: t("Опишите задачу своими словами или голосом — заявку заполню я") },
          { to: "/advisor", e: "🧭", t: t("Подобрать кредит"), d: t("Ответьте на 5 вопросов — подберу продукт под задачу") },
          { to: "/precheck", e: "🎯", t: t("Каковы мои шансы?"), d: t("Оценка готовности до подачи, без запроса в БКИ") },
          { to: "/advisor?calc=1", e: "🧮", t: t("Калькулятор"), d: t("Платёж, переплата и подбор под комфортный платёж") },
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
              <h3>{t("Заявка")} {a.number} · {a.product_name ?? t("продукт не выбран")}</h3>
              <p className="muted small">{a.amount ? money(a.amount) : t("сумма не указана")} · {months(a.term_months)}</p>
            </div>
            <div className="row">
              <StatusBadge status={a.status} label={a.status_label} />
              <Link className="btn dark sm" to={`/applications/${a.id}`}>{a.status === "DRAFT" ? t("Продолжить") : t("Подробнее")}</Link>
            </div>
          </div>
          <div className="mt"><Track steps={a.track.steps} current={a.track.current} failed={a.status === "REJECTED"} /></div>
        </div>
      ))}

      <div className="card">
        <h3>{t("Как проходит кредит")}</h3>
        <div className="grid g4 mt">
          {[
            ["1", t("Подбор и расчёт"), t("Альфик подбирает продукт и считает платёж")],
            ["2", t("Заявка за 5 минут"), t("Реквизиты — из ЕГРЮЛ, сведения — из ФНС и БКИ")],
            ["3", t("Решение онлайн"), t("Автоматически или специалистом; иногда — другие условия")],
            ["4", t("Подпись и деньги"), t("Договор подписывается в кабинете, деньги — на счёт")],
          ].map(([n, title, d]) => (
            <div key={n} className="stack" style={{ gap: 4 }}>
              <span className="badge neutral" style={{ alignSelf: "flex-start" }}>{t("Шаг")} {n}</span>
              <b>{title}</b><span className="muted small">{d}</span>
            </div>
          ))}
        </div>
      </div>

      {feed && (
        <div>
          <div className="row between" style={{ marginBottom: 12 }}>
            <h2>{t("Лента Альфика")}</h2>
            <Link to="/feed" className="link">{t("Вся лента →")}</Link>
          </div>
          <div className="grid g3">
            {feed.items.slice(0, 3).map((it: any) => (
              <div className="feed-card" key={it.id}>
                <span className="feed-kind">{({ news: t("Новость"), tip: t("Совет"), offer: t("Предложение"), guide: t("Гид") } as any)[it.kind]}</span>
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
