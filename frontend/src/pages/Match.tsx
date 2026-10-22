import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BadgePercent, Calendar, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, CircleCheck, Clock, FileCheck2, Heart, Info,
  Lightbulb, RotateCcw, Scale, Shield, SlidersHorizontal, Sparkles, Target, Wallet, X, Zap,
} from "lucide-react";
import { api } from "../api";
import { favoritesChanged } from "../components/Layout";
import { ErrorBox, Loader, useCatalog } from "../components/ui";
import { money, months } from "../format";
import { t } from "../i18n";
import { productArt, productIcon, type Deck, type Favorites, type MatchOffer, type MatchProfile } from "../types";

export const PRIORITIES: { code: MatchProfile["priority"]; label: string; hint: string; icon: typeof Zap }[] = [
  { code: "cost", label: t("Низкая переплата"), hint: t("Важнее всего, сколько я заплачу банку"), icon: BadgePercent },
  { code: "speed", label: t("Скорость получения"), hint: t("Деньги нужны как можно быстрее"), icon: Zap },
  { code: "docs", label: t("Минимум документов"), hint: t("Не хочу собирать бумаги"), icon: FileCheck2 },
  { code: "balanced", label: t("Всё одинаково важно"), hint: t("Подобрать сбалансированный вариант"), icon: Scale },
];

const AMOUNTS = [500_000, 1_000_000, 3_000_000, 5_000_000, 10_000_000, 20_000_000];
const TERMS = [6, 12, 24, 36, 60, 84];

/** Выбор «что для вас важнее» — перед первым подбором и в фильтрах. */
export function PriorityPick({ value, onChange }: { value?: string; onChange: (p: MatchProfile["priority"]) => void }) {
  return (
    <div className="priority-pick">
      {PRIORITIES.map((p) => (
        <button key={p.code} className={value === p.code ? "on" : ""} onClick={() => onChange(p.code)}>
          <p.icon size={26} />
          <b>{p.label}</b>
          <small>{p.hint}</small>
        </button>
      ))}
    </div>
  );
}

export function SwipeCardBody({ o }: { o: MatchOffer }) {
  return (
    <>
      <div className="sc-head">
        <div className="sc-icon"><img src={productIcon(o.code)} alt="" /></div>
        <div>
          <h3>{o.name}</h3>
          <p>{o.short}</p>
        </div>
        {o.recommended && <span className="badge rec">{t("Рекомендуем")}</span>}
      </div>
      <div className="sc-amount">
        <div style={{ position: "relative", zIndex: 1 }}>
          <div className="lbl">{t("Сумма кредита")}</div>
          <div className="num">{money(o.amount)}</div>
          <div className="small muted">{t("до {0}", money(o.max_amount))}</div>
        </div>
        <img src={productArt(o.code)} alt="" />
      </div>
      <div className="sc-row">
        <div className="sc-cell"><Calendar size={22} /><div><div className="l">{t("Срок")}</div><div className="v">{months(o.term_months)}</div></div></div>
        <div className="sc-cell"><Wallet size={22} /><div>
          <div className="l">{o.revolving ? t("Проценты в месяц") : t("Платёж от")}</div>
          <div className="v cyan">{money(o.monthly_payment)}</div>
        </div></div>
      </div>
      <div className="sc-row">
        <div className="sc-cell"><BadgePercent size={22} /><div><div className="l">{t("Ставка")}</div><div className="v">{t("от {0}%", o.rate)}</div></div></div>
        <div className="sc-cell"><Clock size={22} /><div><div className="l">{t("Решение")}</div><div className="v" style={{ fontSize: 15 }}>{o.decision_time}</div></div></div>
      </div>
      <div className="sc-note">{t("Предварительный расчёт. Точные условия — после рассмотрения заявки")}</div>
      <div className="sc-why">
        <h4>{t("Почему подходит именно вам")}</h4>
        <ul>
          {o.fits.slice(0, 3).map((f) => <li key={f}><CircleCheck size={18} className="ok-i" />{f}</li>)}
          {o.gaps.slice(0, 1).map((g) => <li key={g} className="muted"><CircleAlert size={18} className="gap-i" />{g}</li>)}
        </ul>
      </div>
    </>
  );
}

function FilterPill({ icon: Icon, label, value, children }: {
  icon: typeof Target; label: string; value: string; children: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="filter-pill" onClick={() => setOpen(!open)}>
        <span className="ic"><Icon size={18} /></span><span className="muted">{label}:</span><b>{value}</b><ChevronDown size={16} />
      </button>
      {open && <div className="filter-pop">{children(() => setOpen(false))}</div>}
    </div>
  );
}

export default function Match() {
  const nav = useNavigate();
  const catalog = useCatalog();
  const [deck, setDeck] = useState<Deck | null>(null);
  const [compareCount, setCompareCount] = useState(0);
  const [idx, setIdx] = useState(0);
  const [drag, setDrag] = useState<{ x0: number; dx: number } | null>(null);
  const [leaving, setLeaving] = useState<"left" | "right" | null>(null);
  const [error, setError] = useState<any>(null);
  const [toast, setToast] = useState<string | null>(null);

  const loadFavs = () => api<Favorites>("/api/favorites").then((f) => setCompareCount(f.compare_count)).catch(() => {});
  useEffect(() => {
    api<Deck>("/api/match").then(setDeck).catch(setError);
    loadFavs();
  }, []);

  const update = async (patch: Partial<MatchProfile> & { reset_swipes?: boolean }) => {
    setError(null);
    try {
      setDeck(await api<Deck>("/api/match/profile", { method: "PUT", body: patch }));
      setIdx(0);
    } catch (e) { setError(e); }
  };

  const cards = deck?.deck ?? [];
  const current = cards[Math.min(idx, cards.length - 1)];

  const swipe = useCallback(async (action: "like" | "skip") => {
    if (!current || leaving) return;
    setLeaving(action === "like" ? "right" : "left");
    try {
      const [next] = await Promise.all([
        api<Deck>("/api/match/swipe", { body: { product_code: current.code, action } }),
        new Promise((r) => setTimeout(r, 280)),
      ]);
      setDeck(next);
      setIdx((i) => Math.min(i, Math.max(0, next.deck.length - 1)));
      if (action === "like") {
        setToast(t("«{0}» — в избранном", current.name));
        favoritesChanged();
        loadFavs();
      }
    } catch (e) { setError(e); }
    setLeaving(null);
    setDrag(null);
  }, [current, leaving]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") swipe("like");
      if (e.key === "ArrowLeft") swipe("skip");
      if (e.key === "Enter" && current) nav(`/offers/${current.code}`);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [swipe, current, nav]);

  if (!deck) return error ? <ErrorBox error={error} /> : <Loader />;
  const prof = deck.profile;

  if (!deck.configured) {
    return (
      <div className="stack lg">
        <div className="page-head">
          <div>
            <h1>{t("Найдём кредит для вашего бизнеса")}</h1>
            <p>{t("Сначала скажите, что для вас важнее, — я выстрою предложения под это, а не под выгоду банка")}</p>
          </div>
        </div>
        <div className="card glow stack lg">
          <h2>{t("Что для вас важнее всего?")}</h2>
          <PriorityPick value={undefined} onChange={(p) => update({ priority: p })} />
          <p className="muted small">{t("Дальше листайте карточки: вправо — в избранное, влево — пропустить. После нескольких выборов я уточню ваши предпочтения.")}</p>
        </div>
      </div>
    );
  }

  const dx = drag?.dx ?? 0;
  const style = leaving ? undefined : { transform: `translateX(${dx}px) rotate(${dx / 22}deg)` };
  const purposeLabel = catalog?.purposes.find((p) => p.code === prof.purpose)?.label ?? prof.purpose;
  const total = deck.stats.total;
  const done = deck.stats.liked + deck.stats.skipped;

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Найдём кредит для вашего бизнеса")}</h1>
          <p>{t("Подберём оптимальные условия под ваши цели и возможности")}</p>
        </div>
      </div>

      <div className="filters">
        <FilterPill icon={Target} label={t("Цель")} value={purposeLabel.split(" (")[0]}>
          {(close) => catalog?.purposes.map((p) => (
            <button key={p.code} className={`opt ${p.code === prof.purpose ? "on" : ""}`} onClick={() => { close(); update({ purpose: p.code }); }}>{p.label}</button>
          ))}
        </FilterPill>
        <FilterPill icon={Wallet} label={t("Сумма")} value={money(prof.amount)}>
          {(close) => AMOUNTS.map((a) => (
            <button key={a} className={`opt ${a === prof.amount ? "on" : ""}`} onClick={() => { close(); update({ amount: a }); }}>{money(a)}</button>
          ))}
        </FilterPill>
        <FilterPill icon={Calendar} label={t("Срок")} value={months(prof.term_months)}>
          {(close) => TERMS.map((m) => (
            <button key={m} className={`opt ${m === prof.term_months ? "on" : ""}`} onClick={() => { close(); update({ term_months: m }); }}>{months(m)}</button>
          ))}
        </FilterPill>
        <FilterPill icon={Shield} label={t("Залог")} value={prof.has_collateral ? t("Есть") : t("Без залога")}>
          {(close) => [false, true].map((v) => (
            <button key={String(v)} className={`opt ${v === prof.has_collateral ? "on" : ""}`} onClick={() => { close(); update({ has_collateral: v }); }}>
              {v ? t("Есть залог — ставка ниже") : t("Без залога")}
            </button>
          ))}
        </FilterPill>
        <FilterPill icon={Sparkles} label={t("Важнее")} value={deck.priority_label}>
          {(close) => PRIORITIES.map((p) => (
            <button key={p.code} className={`opt ${p.code === prof.priority ? "on" : ""}`} onClick={() => { close(); update({ priority: p.code }); }}>{p.label}</button>
          ))}
        </FilterPill>
        <button className="btn ghost" onClick={() => nav("/match/params")}><SlidersHorizontal size={18} />{t("Изменить параметры")}</button>
      </div>

      {deck.insight && <div className="insight"><Lightbulb size={20} />{deck.insight}</div>}
      <ErrorBox error={error} />

      <div className="match-grid">
        <div>
          {current ? (
            <div className="deck">
              <button className="round-btn nav prev" aria-label={t("Предыдущее предложение")} disabled={idx === 0} onClick={() => setIdx(idx - 1)}><ChevronLeft /></button>
              {cards[idx - 1] && (
                <div className="side left card neon" onClick={() => setIdx(idx - 1)}><SideMini o={cards[idx - 1]} /></div>
              )}
              {cards[idx + 1] && (
                <div className="side right card neon" onClick={() => setIdx(idx + 1)}><SideMini o={cards[idx + 1]} /></div>
              )}
              <div
                key={current.code}
                className={`swipe-card ${drag ? "dragging" : ""} ${leaving === "right" ? "out-right" : leaving === "left" ? "out-left" : ""}`}
                style={style}
                onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); setDrag({ x0: e.clientX, dx: 0 }); }}
                onPointerMove={(e) => drag && setDrag({ ...drag, dx: e.clientX - drag.x0 })}
                onPointerUp={() => {
                  if (!drag) return;
                  if (drag.dx > 110) swipe("like");
                  else if (drag.dx < -110) swipe("skip");
                  else { if (Math.abs(drag.dx) < 6) nav(`/offers/${current.code}`); setDrag(null); }
                }}
                onPointerCancel={() => setDrag(null)}
              >
                <span className="swipe-stamp like" style={{ opacity: Math.max(0, Math.min(1, dx / 110)) }}>{t("В ИЗБРАННОЕ")}</span>
                <span className="swipe-stamp skip" style={{ opacity: Math.max(0, Math.min(1, -dx / 110)) }}>{t("ПРОПУСК")}</span>
                <SwipeCardBody o={current} />
                <div className="match-meter mt">
                  <span>{t("Совпадение с вашими требованиями")}</span>
                  <div className="fit-bar" style={{ flex: 1 }}><div style={{ width: `${current.match_percent ?? 0}%` }} /></div>
                  <b>{current.match_percent}%</b>
                </div>
              </div>
              <button className="round-btn nav next" aria-label={t("Следующее предложение")} disabled={idx >= cards.length - 1} onClick={() => setIdx(idx + 1)}><ChevronRight /></button>
            </div>
          ) : (
            <div className="card glow empty">
              <img src="/brand/alfik-jump.webp" alt="" className="bob" style={{ width: 170 }} />
              <h2>{t("Вы просмотрели все предложения")}</h2>
              <p className="mt">{t("Понравившиеся варианты — в избранном. Сравните их или начните подбор заново.")}</p>
              <div className="row mt" style={{ justifyContent: "center" }}>
                <button className="btn primary" onClick={() => nav("/favorites")}><Heart size={18} />{t("Открыть избранное")}</button>
                <button className="btn ghost" onClick={() => update({ reset_swipes: true })}><RotateCcw size={18} />{t("Начать заново")}</button>
              </div>
            </div>
          )}
          <div className="deck-progress">
            {Array.from({ length: total }).map((_, i) => <i key={i} className={i < done ? "done" : i === done ? "on" : ""} />)}
          </div>
          <p className="muted small" style={{ textAlign: "center", marginTop: 8 }}>
            {t("Перетащите карточку или нажмите ← / → на клавиатуре. Нажатие на карточку — подробности.")}
          </p>
        </div>

        <div className="card helper-panel">
          <div className="hp-art"><img src="/brand/alfik-jump.webp" alt={t("Альфик")} /></div>
          <h3>{t("Ваш помощник в выборе кредита")}</h3>
          <p className="muted small">{t("Анализирую ваш бизнес и подбираю лучшие решения")}</p>
          <div className="helper-item"><Target size={20} />{t("Подбираем по вашим параметрам")}</div>
          <div className="helper-item"><Scale size={20} />{t("Сравниваем условия честно — без выгоды банка в рейтинге")}</div>
          <div className="helper-item"><Sparkles size={20} />{t("Учитываем ваши предпочтения: {0}", deck.priority_label.toLowerCase())}</div>
          <div className="helper-item"><Shield size={20} />{t("Без скрытых платежей и комиссий")}</div>
          <div className="row between small muted">
            <span>{t("Просмотрено {0} из {1}", done, total)}</span>
            {done > 0 && <button className="link" onClick={() => update({ reset_swipes: true })}>{t("Начать заново")}</button>}
          </div>
        </div>
      </div>

      <div className="swipe-actions">
        <button className="btn outline-red" disabled={!current} onClick={() => swipe("skip")}><X size={22} />{t("Пропустить")}</button>
        <button className="btn cyan" disabled={!current} onClick={() => swipe("like")}><Heart size={22} />{t("В избранное")}</button>
        <button className="btn violet" disabled={!current} onClick={() => current && nav(`/offers/${current.code}`)}><Info size={22} />{t("Подробнее")}</button>
        <button className="btn primary" onClick={() => nav("/favorites?compare=1")}><Scale size={22} />{t("Сравнить предложения")}<span className="count">{compareCount}</span></button>
      </div>

      {toast && (
        <div className="alert ok" style={{ position: "fixed", bottom: 30, left: "50%", transform: "translateX(-50%)", zIndex: 80, boxShadow: "0 10px 40px rgba(0,0,0,.6)" }}>
          <Heart size={16} style={{ verticalAlign: -3, marginRight: 6 }} />{toast}
        </div>
      )}
    </div>
  );
}

function SideMini({ o }: { o: MatchOffer }) {
  return (
    <div className="stack" style={{ gap: 10, height: "100%" }}>
      <div className="row nowrap"><div className="sc-icon" style={{ width: 48, height: 48 }}><img src={productIcon(o.code)} alt="" style={{ width: 40, height: 40 }} /></div><b>{o.name}</b></div>
      <div className="tile"><div className="small muted">{t("Сумма кредита")}</div><b style={{ fontSize: 20 }}>{money(o.amount)}</b></div>
      <div className="tile"><div className="small muted">{t("Срок")}</div><b>{months(o.term_months)}</b></div>
      <div className="tile"><div className="small muted">{t("Платёж от")}</div><b className="cyan">{money(o.monthly_payment)}</b></div>
      <img src={productArt(o.code)} alt="" style={{ width: "100%", marginTop: "auto", borderRadius: 12, maxHeight: 90, objectFit: "cover" }} />
    </div>
  );
}
