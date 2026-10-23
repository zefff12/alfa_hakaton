import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, CircleHelp, FileText, Headphones, Lightbulb, Sparkles } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { openAlfik } from "../components/Chat";
import { StepsTimeline, TaskList } from "../components/Progress";
import { StatusBadge, useCatalog } from "../components/ui";
import { dateTime, money, months } from "../format";
import { t } from "../i18n";
import { productIcon, type Application } from "../types";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? t("Доброй ночи") : h < 12 ? t("Доброе утро") : h < 18 ? t("Добрый день") : t("Добрый вечер");
}

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const catalog = useCatalog();
  const [apps, setApps] = useState<Application[] | null>(null);
  const [capacity, setCapacity] = useState<{ amount: number | null; source: string | null } | null>(null);
  const [feed, setFeed] = useState<any>(null);

  useEffect(() => {
    api<Application[]>("/api/applications").then(setApps).catch(() => setApps([]));
    api("/api/me/capacity").then(setCapacity).catch(() => {});
    api("/api/feed").then(setFeed).catch(() => {});
  }, []);

  const name = user?.full_name.split(" ")[0];
  const active = apps?.filter((a) => !a.is_final) ?? [];
  const focus = active[0];

  return (
    <div className="stack lg">
      <section className="hero home">
        <div>
          <h1>{greeting()},<br />{name}!</h1>
          <p>{focus
            ? t("Заявка {0}: {1}. {2}", focus.number, focus.status_label.toLowerCase(), focus.alfik.todo ? t("От вас: {0}.", focus.alfik.todo.toLowerCase()) : t("От вас ничего не нужно — я слежу за ней."))
            : t("Помогаем вам развивать бизнес с удобным финансированием")}</p>
          {focus && <button className="btn ghost mt" onClick={() => nav(`/applications/${focus.id}`)}>{t("Открыть заявку")}<ChevronRight size={18} /></button>}
        </div>
        <img src="/brand/alfik-jump.webp" alt={t("Альфик")} className="bob" style={{ width: 230 }} />
        <div className="card hero-cta">
          <h3 style={{ fontSize: 20 }}>{t("Подберите финансирование под ваши цели")}</h3>
          <p className="text-2 small" style={{ marginTop: 8 }}>{t("Получите персональные условия за 2 минуты")}</p>
          <button className="btn primary block mt" onClick={() => nav("/match")}>{t("Подобрать кредит")}</button>
        </div>
      </section>

      <div className="quick-products">
        {catalog?.products.map((p) => (
          <button key={p.code} className="qp" onClick={() => nav(`/offers/${p.code}`)}>
            <img src={productIcon(p.code)} alt="" />
            <div style={{ flex: 1, minWidth: 0 }}><b>{p.name}</b><small>{p.short}</small></div>
            <ChevronRight size={16} className="muted" />
          </button>
        ))}
      </div>

      <div className="split-2">
        <div className="card">
          <div className="row between" style={{ marginBottom: 8 }}>
            <h2>{t("Мои заявки")}</h2>
            <Link to="/applications" className="link">{t("Все заявки")} →</Link>
          </div>
          {apps && apps.length === 0 && (
            <div className="empty" style={{ padding: 18 }}>
              <p>{t("Заявок пока нет — подберём кредит?")}</p>
              <button className="btn primary mt" onClick={() => nav("/match")}>{t("Подобрать кредит")}</button>
            </div>
          )}
          <table className="tbl">
            <tbody>
              {(apps ?? []).slice(0, 4).map((a) => (
                <tr key={a.id} className="click" onClick={() => nav(`/applications/${a.id}`)}>
                  <td style={{ width: 52 }}>{a.product_code && <img src={productIcon(a.product_code)} alt="" style={{ width: 40, height: 40, objectFit: "contain" }} />}</td>
                  <td><b>{a.product_name ?? t("Продукт не выбран")}</b><div className="small muted">{a.number} · {dateTime(a.created_at)}</div></td>
                  <td style={{ whiteSpace: "nowrap" }}><b>{money(a.amount)}</b><div className="small muted">{months(a.term_months)}</div></td>
                  <td><StatusBadge status={a.status} label={a.status_label} /></td>
                  <td><ChevronRight size={18} className="muted" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card capacity stack">
          <div className="row nowrap"><h2>{t("Мои возможности")}</h2><CircleHelp size={18} className="muted" /></div>
          <div className="text-2">{capacity?.source === "scoring" ? t("Одобренная сумма по последней оценке") : t("Предварительно одобренная сумма")}</div>
          <div style={{ fontSize: 34, fontWeight: 800 }}>{capacity?.amount ? t("до {0}", money(capacity.amount)) : "—"}</div>
          <div className="bar" />
          <p className="muted small">{capacity?.source === "fns"
            ? t("Ориентир по выручке из ФНС. Точная сумма будет рассчитана после рассмотрения заявки.")
            : t("Точная сумма будет рассчитана после рассмотрения заявки.")}</p>
          <button className="btn ghost sm" style={{ alignSelf: "flex-start" }} onClick={() => nav("/precheck")}>{t("Узнать шансы на одобрение")}</button>
        </div>
      </div>

      {focus && focus.status !== "DRAFT" && (
        <div className="card glow">
          <div className="row between" style={{ marginBottom: 14 }}>
            <h2>{t("Заявка {0}: где она сейчас", focus.number)}</h2>
            <StatusBadge status={focus.status} label={focus.status_label} />
          </div>
          <div className="grid g2">
            <StepsTimeline steps={focus.steps} />
            <div className="stack">
              {focus.alfik.say && <div className="bubble"><b className="name">{t("Альфик")}</b>{focus.alfik.say}</div>}
              <TaskList app={focus} tasks={focus.tasks} />
            </div>
          </div>
        </div>
      )}

      <div className="grid g3">
        <button className="action-tile" style={{ flexDirection: "row", alignItems: "center", gap: 14 }} onClick={() => nav("/documents")}>
          <span className="avatar-ring"><FileText size={20} /></span>
          <div style={{ flex: 1 }}><b>{t("Документы")}</b><span style={{ display: "block" }}>{t("Загрузите документы заранее, чтобы ускорить рассмотрение")}</span></div>
          <ChevronRight size={18} />
        </button>
        <button className="action-tile" style={{ flexDirection: "row", alignItems: "center", gap: 14, background: "linear-gradient(100deg, rgba(110,60,255,.55), rgba(40,150,255,.35) 60%, rgba(255,200,60,.35))", borderColor: "rgba(155,92,255,.6)" }} onClick={() => nav("/match")}>
          <span className="avatar-ring"><Sparkles size={20} /></span>
          <div style={{ flex: 1 }}><b>{t("Персональная подборка")}</b><span style={{ display: "block", color: "var(--text-2)" }}>{t("Продукты на основе данных о вашем бизнесе")}</span></div>
          <ChevronRight size={18} />
        </button>
        <button className="action-tile" style={{ flexDirection: "row", alignItems: "center", gap: 14 }} onClick={() => openAlfik()}>
          <span className="avatar-ring"><Headphones size={20} /></span>
          <div style={{ flex: 1 }}><b>{t("Поддержка")}</b><span style={{ display: "block" }}>{t("Отвечаем в чате — Альфик всегда на связи")}</span></div>
          <ChevronRight size={18} />
        </button>
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
                <div className="why"><Lightbulb size={14} style={{ flexShrink: 0 }} /> {it.why}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
