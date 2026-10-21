import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { dateTime } from "../format";
import Chat from "./Chat";

const CLIENT_NAV = [
  { to: "/", label: "Главная", ico: "🏠", end: true },
  { to: "/advisor", label: "Подобрать кредит", ico: "🧭" },
  { to: "/precheck", label: "Мои шансы", ico: "🎯" },
  { to: "/applications", label: "Мои заявки", ico: "📄" },
  { to: "/feed", label: "Лента Альфика", ico: "📰" },
];
const BANK_NAV = [
  { to: "/bank", label: "Очередь заявок", ico: "📥", end: true },
  { to: "/bank/audit", label: "Журнал событий", ico: "🧾" },
];

function Notifications() {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    const load = () => api<any[]>("/api/notifications").then(setItems).catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  const unread = items.filter((i) => !i.is_read).length;
  return (
    <div className="notif-wrap">
      <button className="icon-btn" onClick={() => {
        setOpen(!open);
        if (!open && unread) api("/api/notifications/read-all", { method: "POST" }).catch(() => {});
      }} aria-label="Уведомления">
        🔔{unread > 0 && <span className="dot" />}
      </button>
      {open && (
        <div className="dropdown" onMouseLeave={() => setOpen(false)}>
          {items.length === 0 && <div className="n-item muted">Уведомлений пока нет</div>}
          {items.map((n) => (
            <div key={n.id} className={`n-item ${n.is_read ? "" : "unread"}`} onClick={() => {
              setOpen(false);
              if (n.application_id) nav(user?.role === "underwriter" ? `/bank/applications/${n.application_id}` : `/applications/${n.application_id}`);
            }}>
              <b>{n.title}</b>
              {n.body && <div className="small muted">{n.body}</div>}
              <div className="small muted">{dateTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout({ bank }: { bank?: boolean }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const items = bank ? BANK_NAV : CLIENT_NAV;
  const initials = user?.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("") ?? "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">А</div>
          <div>Кредитный кабинет<small>{bank ? "консоль специалиста" : "для бизнеса"}</small></div>
        </div>
        {items.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <span className="ico">{i.ico}</span>{i.label}
          </NavLink>
        ))}
        <div className="sidebar-foot">
          {bank ? "Демо-консоль андеррайтера. Данные синтетические." : "Прототип для хакатона. Все данные и условия — синтетические."}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="hello">
            Здравствуйте, {user?.full_name.split(" ")[0]}!
            <small>{bank ? user?.position : user?.company?.name}</small>
          </div>
          <div className="row">
            <Notifications />
            <div className="user-chip">
              <div className="avatar">{initials}</div>
              <button className="btn ghost sm" onClick={() => { logout(); nav("/login"); }}>Выйти</button>
            </div>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
      {!bank && <Chat />}
    </div>
  );
}
