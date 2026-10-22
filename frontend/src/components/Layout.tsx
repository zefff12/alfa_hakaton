import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Bell, ChevronDown, ChevronRight, FileText, FolderOpen, Heart, History, House, Inbox, Layers, LifeBuoy, LogOut,
  Mic, Newspaper, Package, Search, Target, User as UserIcon, WandSparkles, type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { dateTime, money } from "../format";
import Chat, { openAlfik } from "./Chat";
import { t } from "../i18n";
import LangSwitch from "./LangSwitch";
import { useCatalog } from "./ui";

interface NavItem { to: string; label: string; icon: LucideIcon; end?: boolean; badge?: "notifications" | "favorites" }

const CLIENT_NAV: (NavItem | "sep")[] = [
  { to: "/", label: t("Главная"), icon: House, end: true },
  { to: "/advisor", label: t("Подобрать кредит"), icon: WandSparkles },
  { to: "/match", label: t("Кредитный подбор"), icon: Layers },
  { to: "/favorites", label: t("Избранные"), icon: Heart, badge: "favorites" },
  { to: "/applications", label: t("Мои заявки"), icon: FileText },
  { to: "/products", label: t("Продукты"), icon: Package },
  { to: "/documents", label: t("Документы"), icon: FolderOpen },
  { to: "/notifications", label: t("Уведомления"), icon: Bell, badge: "notifications" },
  { to: "/support", label: t("Поддержка"), icon: LifeBuoy },
  "sep",
  { to: "/talk", label: t("Рассказать Альфику"), icon: Mic },
  { to: "/precheck", label: t("Мои шансы"), icon: Target },
  { to: "/feed", label: t("Лента Альфика"), icon: Newspaper },
];
const BANK_NAV: NavItem[] = [
  { to: "/bank", label: t("Очередь заявок"), icon: Inbox, end: true },
  { to: "/bank/audit", label: t("Журнал событий"), icon: History },
];

export interface Notification {
  id: number; application_id: number | null; title: string; body: string; is_read: boolean; created_at: string;
}

/** Уведомления: одна загрузка на кабинет — для колокольчика, счётчика в меню и страницы уведомлений. */
function useNotifications() {
  const [items, setItems] = useState<Notification[]>([]);
  useEffect(() => {
    const load = () => api<Notification[]>("/api/notifications").then(setItems).catch(() => {});
    load();
    const timer = setInterval(load, 8000);
    window.addEventListener("notifications:changed", load);
    return () => { clearInterval(timer); window.removeEventListener("notifications:changed", load); };
  }, []);
  const readAll = () => {
    setItems((list) => list.map((n) => ({ ...n, is_read: true })));
    api("/api/notifications/read-all", { method: "POST" }).catch(() => {});
  };
  return { items, unread: items.filter((i) => !i.is_read).length, readAll };
}

/** Счётчик избранного обновляется по событию от экранов подбора. */
function useFavoritesCount(enabled: boolean) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const load = () => api<{ items: unknown[] }>("/api/favorites").then((f) => setCount(f.items.length)).catch(() => {});
    load();
    window.addEventListener("favorites:changed", load);
    return () => window.removeEventListener("favorites:changed", load);
  }, [enabled]);
  return count;
}

export const favoritesChanged = () => window.dispatchEvent(new Event("favorites:changed"));

function useOutside(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [onClose]);
  return ref;
}

function Bellmenu({ n, bank }: { n: ReturnType<typeof useNotifications>; bank?: boolean }) {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const ref = useOutside(() => setOpen(false));
  return (
    <div className="notif-wrap" ref={ref}>
      <button className="icon-btn" aria-label={t("Уведомления")} onClick={() => {
        setOpen(!open);
        if (!open && n.unread) n.readAll();
      }}>
        <Bell size={20} />{n.unread > 0 && <span className="dot" />}
      </button>
      {open && (
        <div className="dropdown">
          {n.items.length === 0 && <div className="n-item muted">{t("Уведомлений пока нет")}</div>}
          {n.items.slice(0, 8).map((x) => (
            <div key={x.id} className={`n-item ${x.is_read ? "" : "unread"}`} onClick={() => {
              setOpen(false);
              if (x.application_id) nav(bank ? `/bank/applications/${x.application_id}` : `/applications/${x.application_id}`);
            }}>
              <b>{x.title}</b>
              {x.body && <div className="small muted">{x.body}</div>}
              <div className="small muted">{dateTime(x.created_at)}</div>
            </div>
          ))}
          {!bank && (
            <button className="menu-item" style={{ justifyContent: "center", color: "var(--cyan)" }}
              onClick={() => { setOpen(false); nav("/notifications"); }}>{t("Все уведомления")}</button>
          )}
        </div>
      )}
    </div>
  );
}

function UserMenu({ bank, children, up }: { bank?: boolean; children: ReactNode; up?: boolean }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <div onClick={() => setOpen(!open)}>{children}</div>
      {open && (
        <div className="dropdown" style={up ? { top: "auto", bottom: 64, left: 0, right: "auto", width: 260 } : { width: 280 }}>
          <div className="n-item" style={{ cursor: "default" }}>
            <b>{user?.full_name}</b>
            <div className="small muted">{bank ? user?.position : user?.company?.name}</div>
            {!bank && user?.company && <div className="small muted">{t("ИНН")} {user.company.inn}</div>}
          </div>
          {!bank && (
            <>
              <button className="menu-item" onClick={() => { setOpen(false); nav("/applications"); }}><FileText size={18} />{t("Мои заявки")}</button>
              <button className="menu-item" onClick={() => { setOpen(false); nav("/documents"); }}><FolderOpen size={18} />{t("Документы")}</button>
            </>
          )}
          <button className="menu-item" onClick={() => { logout(); nav("/login"); }}><LogOut size={18} />{t("Выйти")}</button>
        </div>
      )}
    </div>
  );
}

interface Hit { group: string; title: string; sub?: string; to: string }

/** Поиск по продуктам, заявкам, документам и разделам кабинета. */
function GlobalSearch({ bank }: { bank?: boolean }) {
  const nav = useNavigate();
  const catalog = useCatalog();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [apps, setApps] = useState<any[] | null>(null);
  const [cursor, setCursor] = useState(0);
  const ref = useOutside(() => setOpen(false));

  // При каждом открытии поиска — свежие заявки и документы
  const loadApps = () => {
    api<any[]>(bank ? "/api/bank/applications" : "/api/applications").then(setApps).catch(() => setApps([]));
  };

  const hits = useMemo<Hit[]>(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const has = (...xs: (string | null | undefined)[]) => xs.some((x) => x?.toLowerCase().includes(s));
    const out: Hit[] = [];
    if (!bank) {
      for (const p of catalog?.products ?? []) {
        if (has(p.name, p.short, p.description)) out.push({ group: t("Продукты"), title: p.name, sub: p.short, to: `/offers/${p.code}` });
      }
    }
    for (const a of apps ?? []) {
      const company = a.company?.name ?? a.company_name;
      if (has(a.number, a.product_name, a.status_label, company)) {
        out.push({ group: t("Заявки"), title: `${a.number} · ${a.product_name ?? "—"}`, sub: `${a.status_label} · ${money(a.amount)}${company ? " · " + company : ""}`,
          to: bank ? `/bank/applications/${a.id}` : `/applications/${a.id}` });
      }
      for (const d of a.documents ?? []) {
        if (has(d.label, d.filename)) out.push({ group: t("Документы"), title: d.label, sub: `${d.filename} · ${a.number}`, to: `/documents?app=${a.id}` });
      }
    }
    const pages = bank ? BANK_NAV : CLIENT_NAV.filter((x): x is NavItem => x !== "sep");
    for (const p of pages) if (has(p.label)) out.push({ group: t("Разделы"), title: p.label, to: p.to });
    return out.slice(0, 12);
  }, [q, catalog, apps, bank]);

  const go = (h: Hit) => { setOpen(false); setQ(""); nav(h.to); };

  return (
    <div className="search" ref={ref}>
      <Search size={19} />
      <input value={q} placeholder={bank ? t("Поиск по заявкам и компаниям") : t("Поиск по продуктам, заявкам, документам")}
        onFocus={() => { setOpen(true); loadApps(); }}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setCursor(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, hits.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
          if (e.key === "Enter" && hits[cursor]) go(hits[cursor]);
          if (e.key === "Escape") setOpen(false);
        }} aria-label={t("Поиск")} />
      {open && q.trim() && (
        <div className="search-results">
          {hits.length === 0 && <div className="n-item muted">{t("Ничего не нашлось")}</div>}
          {hits.map((h, i) => (
            <div key={`${i}-${h.to}`}>
              {(i === 0 || hits[i - 1].group !== h.group) && <div className="grp">{h.group}</div>}
              <button className={i === cursor ? "on" : ""} onMouseEnter={() => setCursor(i)} onClick={() => go(h)}>
                <div style={{ flex: 1, minWidth: 0 }}><b>{h.title}</b>{h.sub && <small>{h.sub}</small>}</div>
                <ChevronRight size={16} className="muted" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout({ bank }: { bank?: boolean }) {
  const { user } = useAuth();
  const loc = useLocation();
  const n = useNotifications();
  const favCount = useFavoritesCount(!bank);
  const items = bank ? BANK_NAV : CLIENT_NAV;
  const company = user?.company?.name;

  useEffect(() => { window.scrollTo({ top: 0 }); }, [loc.pathname]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to={bank ? "/bank" : "/"} className="logo">
          <b>{t("Альфа Банк")}</b><i />
          <small>{bank ? t("консоль кредитного специалиста") : t("кредитный кабинет для бизнеса")}</small>
        </NavLink>
        {items.map((i, idx) => i === "sep" ? <div key={`sep${idx}`} className="nav-sep" /> : (
          <NavLink key={i.to} to={i.to} end={i.end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <i.icon size={21} strokeWidth={1.7} />{i.label}
            {i.badge === "notifications" && n.unread > 0 && <span className="nav-badge">{n.unread}</span>}
            {i.badge === "favorites" && favCount > 0 && <span className="nav-badge" style={{ background: "rgba(47,211,255,.25)", boxShadow: "none" }}>{favCount}</span>}
          </NavLink>
        ))}
        <div className="spacer" />
        {!bank && (
          <button className="helper-card" onClick={() => openAlfik()}>
            <b>{t("Персональный помощник всегда рядом")}</b>
            <span className="go"><ChevronRight size={18} /></span>
            <img src="/brand/alfik-jump.webp" alt={t("Альфик")} />
          </button>
        )}
        <UserMenu bank={bank} up>
          <button className="profile-card">
            <span className="avatar-ring"><UserIcon size={20} /></span>
            <span className="who">
              <b>{bank ? t("Альфа Банк") : company}</b>
              <small>{user?.full_name}</small>
            </span>
            <ChevronDown size={16} className="muted" />
          </button>
        </UserMenu>
      </aside>
      <div className="main">
        <header className="topbar">
          <GlobalSearch bank={bank} />
          <div className="spacer" />
          <LangSwitch />
          <Bellmenu n={n} bank={bank} />
          <UserMenu bank={bank}>
            <button className="user-chip">
              <span className="avatar-ring" style={{ width: 42, height: 42 }}><UserIcon size={20} /></span>
              <span className="who-top">{user?.full_name}</span>
              <ChevronDown size={16} />
            </button>
          </UserMenu>
        </header>
        <main className="content">
          <Outlet context={{ notifications: n }} />
        </main>
      </div>
      {!bank && loc.pathname !== "/talk" && <Chat />}
    </div>
  );
}
