import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BadgePercent, Calendar, Check, CircleHelp, Clock, Coins, FileText, Heart, Layers, Rocket, Scale, Shield, Sparkles,
  Target, Trash2, Wallet, X, Zap, type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { openAlfik } from "../components/Chat";
import { favoritesChanged } from "../components/Layout";
import { ErrorBox, Loader } from "../components/ui";
import { money, months } from "../format";
import { t } from "../i18n";
import { productArt, productIcon, type Application, type Favorites as Favs } from "../types";

const ROW_ICON: Record<string, LucideIcon> = {
  purpose: Target, amount: Wallet, term: Calendar, rate: BadgePercent, payment: Coins, total: Layers, collateral: Shield,
  speed: Clock, form: FileText, early: Zap, feature: Sparkles,
};

interface Compare {
  rows: { key: string; label: string }[];
  columns: { code: string; name: string; short: string; recommended: boolean; cells: Record<string, string> }[];
  best: Record<string, string>;
}

export function useApplyOffer() {
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<any>(null);
  const apply = async (code: string, amount?: number, term?: number) => {
    setBusy(code);
    setError(null);
    try {
      const app = await api<Application>(`/api/offers/${code}/apply`, { body: { amount, term_months: term } });
      nav(`/applications/${app.id}`);
    } catch (e) { setError(e); setBusy(null); }
  };
  return { apply, busy, error };
}

export function CompareModal({ codes, onClose }: { codes?: string[]; onClose: () => void }) {
  const nav = useNavigate();
  const [data, setData] = useState<Compare | null>(null);
  const [error, setError] = useState<any>(null);
  const { apply, busy, error: applyError } = useApplyOffer();
  useEffect(() => {
    api<Compare>(`/api/compare${codes ? `?codes=${codes.join(",")}` : ""}`).then(setData).catch(setError);
  }, [codes]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const cols = data?.columns ?? [];
  const grid = { gridTemplateColumns: `220px repeat(${Math.max(cols.length, 1)}, minmax(170px, 1fr))` };
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={t("Сравнение предложений")}>
        <div className="row between" style={{ marginBottom: 18 }}>
          <div>
            <h1 style={{ fontSize: 32 }}>{t("Сравнение предложений")}</h1>
            <p className="text-2 mt" style={{ marginTop: 6 }}>{t("Сравните условия и выберите лучший вариант для вашего бизнеса")}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label={t("Закрыть")}><X /></button>
        </div>
        <ErrorBox error={error ?? applyError} />
        {data && (
          <div style={{ overflowX: "auto" }}>
            <div className="cmp" style={grid}>
              <div />
              {cols.map((c) => (
                <div key={c.code} className="cmp-head-cell">
                  {c.recommended && <span className="badge rec" style={{ marginBottom: 6 }}>{t("Рекомендуем")}</span>}
                  <h3>{c.name}</h3>
                  <p>{c.short}</p>
                  <img src={productIcon(c.code)} alt="" />
                </div>
              ))}
              {data.rows.map((r) => {
                const Icon = ROW_ICON[r.key] ?? Check;
                return (
                  <div key={r.key} style={{ display: "contents" }}>
                    <div className="cmp-label"><Icon size={18} />{r.label}</div>
                    {cols.map((c) => (
                      <div key={c.code} className={`cmp-cell ${data.best[r.key] === c.code ? "best" : ""}`}>
                        {data.best[r.key] === c.code && <Check size={16} />}{c.cells[r.key]}
                      </div>
                    ))}
                  </div>
                );
              })}
              <div />
              {cols.map((c) => (
                <div key={c.code} className="stack" style={{ gap: 8 }}>
                  <button className="btn primary block" disabled={!!busy} onClick={() => apply(c.code)}>{busy === c.code ? t("Создаю…") : t("Оформить заявку")}</button>
                  <button className="btn ghost block" onClick={() => { onClose(); nav(`/offers/${c.code}`); }}>{t("Подробнее")}</button>
                </div>
              ))}
            </div>
          </div>
        )}
        {!data && !error && <Loader />}
        <div className="cmp-tip">
          <img src="/brand/alfik-jump.webp" alt="" style={{ width: 70 }} />
          <div style={{ flex: 1 }}>
            <b>{t("Не можете определиться?")}</b>
            <p className="text-2 small">{t("Зелёным отмечены лучшие значения в каждой строке. Не нашли подходящий вариант — подберём ещё.")}</p>
          </div>
          <button className="btn gold" onClick={() => { onClose(); nav("/match"); }}>{t("Подобрать ещё")}</button>
        </div>
      </div>
    </div>
  );
}

export default function Favorites() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Favs | null>(null);
  const [tab, setTab] = useState<"all" | "compare">("all");
  const [error, setError] = useState<any>(null);
  const { apply, busy, error: applyError } = useApplyOffer();
  const comparing = params.get("compare") === "1";

  const load = () => api<Favs>("/api/favorites").then(setData).catch(setError);
  useEffect(() => { load(); }, []);

  const act = async (path: string, method: string) => {
    setError(null);
    try { setData(await api<Favs>(path, { method })); favoritesChanged(); } catch (e) { setError(e); }
  };
  const openCompare = () => {
    if ((data?.compare_count ?? 0) < 2) { setError({ message: t("Для сравнения отметьте хотя бы два предложения") }); return; }
    setParams({ compare: "1" });
  };

  if (!data) return error ? <ErrorBox error={error} /> : <Loader />;
  const items = tab === "all" ? data.items : data.items.filter((i) => i.in_compare);

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Избранные кредиты")}</h1>
          <p>{t("Сохраняйте понравившиеся предложения и сравнивайте их")}</p>
        </div>
      </div>
      <div className="row between">
        <div className="pill-tabs">
          <button className={tab === "all" ? "on" : ""} onClick={() => setTab("all")}><Heart size={16} />{t("Избранные")} <span className="count">{data.items.length}</span></button>
          <button className={tab === "compare" ? "on" : ""} onClick={() => setTab("compare")}><Scale size={16} />{t("Сравнение")} <span className="count">{data.compare_count}</span></button>
        </div>
        {data.items.length > 0 && (
          <button className="btn ghost" onClick={() => confirm(t("Очистить избранное?")) && act("/api/favorites", "DELETE")}><Trash2 size={18} />{t("Очистить избранное")}</button>
        )}
      </div>
      <ErrorBox error={error ?? applyError} />

      {data.items.length === 0 ? (
        <div className="card glow empty">
          <img src="/brand/alfik-jump.webp" alt="" className="bob" style={{ width: 160 }} />
          <h2>{t("В избранном пока пусто")}</h2>
          <p className="mt">{t("Листайте предложения в «Кредитном подборе» и сохраняйте понравившиеся свайпом вправо.")}</p>
          <button className="btn primary mt" onClick={() => nav("/match")}>{t("Перейти к подбору")}</button>
        </div>
      ) : (
        <div className="fav-grid">
          <div className="fav-cards">
          {items.map((o) => (
            <div key={o.code} className="fav-card">
              <button className="heart" aria-label={t("Убрать из избранного")} onClick={() => act(`/api/favorites/${o.code}`, "DELETE")}><Heart size={20} fill="currentColor" /></button>
              <div className="row nowrap">
                <div className="sc-icon" style={{ width: 52, height: 52 }}><img src={productIcon(o.code)} alt="" style={{ width: 44, height: 44 }} /></div>
                <div><h3>{o.name}</h3><div className="sub">{o.short}</div></div>
              </div>
              {o.recommended && <span className="badge rec" style={{ alignSelf: "flex-start" }}>{t("Рекомендуем")}</span>}
              <div className="art"><img src={productArt(o.code)} alt="" /></div>
              <div className="fav-row"><Wallet size={20} /><div><div className="l">{t("Сумма кредита")}</div><div className="v">{money(o.amount)}</div></div></div>
              <div className="fav-row"><Calendar size={20} /><div><div className="l">{t("Срок")}</div><div className="v">{months(o.term_months)}</div></div></div>
              <div className="fav-row"><Coins size={20} /><div><div className="l">{o.revolving ? t("Проценты в месяц") : t("Платёж от")}</div><div className="v cyan">{money(o.monthly_payment)}</div></div></div>
              <div className="spacer" />
              <button className="btn primary block" disabled={!!busy} onClick={() => apply(o.code)}>{busy === o.code ? t("Создаю…") : t("Оформить заявку")}</button>
              <div className="two">
                <button className="btn ghost sm" onClick={() => nav(`/offers/${o.code}`)}>{t("Подробнее")}</button>
                <button className={`btn ghost sm ${o.in_compare ? "in-compare" : ""}`} onClick={() => act(`/api/favorites/${o.code}/compare`, "POST")}>
                  {o.in_compare ? <Check size={16} /> : <Scale size={16} />}{o.in_compare ? t("В сравнении") : t("Сравнить")}
                </button>
              </div>
            </div>
          ))}
          </div>
          <div className="stack">
            <div className="card glow stack">
              <Scale size={30} className="cyan" />
              <h3>{t("Сравните кредиты")}</h3>
              <p className="muted small">{t("Отметьте предложения кнопкой «Сравнить» и посмотрите условия рядом.")}</p>
              <button className="btn primary block" onClick={openCompare}>{t("Сравнить выбранные")}<span className="count">{data.compare_count}</span></button>
            </div>
            <div className="card stack">
              <CircleHelp size={28} className="cyan" />
              <h3>{t("Нужна помощь?")}</h3>
              <p className="muted small">{t("Альфик объяснит разницу между предложениями и поможет выбрать.")}</p>
              <button className="btn ghost block" onClick={() => openAlfik(t("Какой кредит мне подойдёт?"))}>{t("Задать вопрос")}</button>
            </div>
            <button className="btn ghost" onClick={() => nav("/match")}><Rocket size={18} />{t("Подобрать ещё")}</button>
          </div>
        </div>
      )}

      {comparing && <CompareModal onClose={() => setParams({})} />}
    </div>
  );
}
