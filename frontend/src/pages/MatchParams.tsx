import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, Briefcase, Building2, Check, ChevronLeft, ChevronRight, Coins, Ellipsis, Pencil, Repeat, Rocket, RotateCcw,
  Truck, Wallet, type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Loader, MoneyInput } from "../components/ui";
import { date, money, months } from "../format";
import { t } from "../i18n";
import type { Deck, MatchProfile } from "../types";
import { PRIORITIES, PriorityPick } from "./Match";

const PURPOSE_TILES: { code: string; label: string; icon: LucideIcon }[] = [
  { code: "expansion", label: t("Развитие бизнеса"), icon: Rocket },
  { code: "working_capital", label: t("Оборотные средства"), icon: Coins },
  { code: "equipment", label: t("Оборудование и транспорт"), icon: Truck },
  { code: "refinance", label: t("Рефинансирование"), icon: Repeat },
  { code: "cash_gap", label: t("Кассовый разрыв"), icon: Wallet },
  { code: "renovation", label: t("Ремонт помещения"), icon: Building2 },
  { code: "contract", label: t("Госконтракт или тендер"), icon: Briefcase },
  { code: "other", label: t("Другое"), icon: Ellipsis },
];
const STEPS = [t("Параметры"), t("О компании"), t("Финансовые данные"), t("Дополнительно")];
const TIPS = [
  t("Чем точнее цель, тем точнее подбор: под оборудование выгоднее инвестиционный кредит, под закупку — оборотный."),
  t("Комфортный платёж — не больше 30% месячной выручки. Если выходит больше, увеличьте срок."),
  t("Залог снижает ставку, но для небольших сумм удобнее экспресс-кредит без залога."),
];
const DEFAULTS: Partial<MatchProfile> = { purpose: "working_capital", amount: 3_000_000, term_months: 24, has_collateral: false, deferral: false, priority: "balanced" };

function YesNo({ value, onChange, no, yes }: { value: boolean; onChange: (v: boolean) => void; no: string; yes: string }) {
  return (
    <div className="pill-tabs">
      <button className={!value ? "on" : ""} onClick={() => onChange(false)}>{no}</button>
      <button className={value ? "on" : ""} onClick={() => onChange(true)}>{yes}</button>
    </div>
  );
}

export default function MatchParams() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [p, setP] = useState<MatchProfile | null>(null);
  const [step, setStep] = useState(0);
  const [tip, setTip] = useState(0);
  const [reset, setReset] = useState(true);
  const [error, setError] = useState<any>(null);

  useEffect(() => { api<Deck>("/api/match").then((d) => setP(d.profile)).catch(setError); }, []);
  if (!p) return error ? <ErrorBox error={error} /> : <Loader />;
  const set = (patch: Partial<MatchProfile>) => setP({ ...p, ...patch });
  const company = user?.company;

  async function save() {
    setError(null);
    try {
      await api("/api/match/profile", { method: "PUT", body: {
        purpose: p!.purpose, amount: p!.amount, term_months: p!.term_months, has_collateral: p!.has_collateral,
        deferral: p!.deferral, priority: p!.priority, monthly_revenue: p!.monthly_revenue || null, reset_swipes: reset,
      } });
      nav("/match");
    } catch (e) { setError(e); }
  }

  const purpose = PURPOSE_TILES.find((x) => x.code === p.purpose);
  const priority = PRIORITIES.find((x) => x.code === p.priority);

  return (
    <div className="stack lg">
      <div>
        <button className="crumb" onClick={() => nav("/match")}><ArrowLeft size={18} />{t("К подбору")}</button>
        <h1>{t("Изменить параметры подбора")}</h1>
        <p className="text-2" style={{ marginTop: 8, fontSize: 18 }}>{t("Уточните информацию, чтобы мы подобрали лучшие предложения для вашего бизнеса")}</p>
      </div>

      <div className="match-grid side-340">
        <div className="card glow stack lg">
          <div className="steps-line">
            {STEPS.map((s, i) => (
              <span key={s} style={{ display: "contents" }}>
                {i > 0 && <span className={`bar ${i <= step ? "on" : ""}`} />}
                <button className={`s ${i === step ? "on" : i < step ? "done" : ""}`} onClick={() => setStep(i)}>
                  <span className="n">{i < step ? <Check size={16} /> : i + 1}</span>{s}
                </button>
              </span>
            ))}
          </div>

          {step === 0 && (
            <>
              <div className="stack">
                <h3>{t("Цель кредита")}</h3>
                <div className="purpose-grid">
                  {PURPOSE_TILES.map((x) => (
                    <button key={x.code} className={`purpose-tile ${p.purpose === x.code ? "on" : ""}`} onClick={() => set({ purpose: x.code })}>
                      <span className="pi"><x.icon size={22} /></span>{x.label}
                      {p.purpose === x.code && <span className="tick"><Check size={14} /></span>}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid g2">
                <div className="stack">
                  <div className="slider-row"><h3>{t("Сумма кредита")}</h3><span className="amount-box">{money(p.amount)}</span></div>
                  <input type="range" min={100_000} max={30_000_000} step={100_000} value={p.amount} onChange={(e) => set({ amount: Number(e.target.value) })} aria-label={t("Сумма кредита")} />
                  <div className="row between small muted"><span>{money(100_000)}</span><span>{money(30_000_000)}</span></div>
                </div>
                <div className="stack">
                  <div className="slider-row"><h3>{t("Срок кредита")}</h3><span className="amount-box">{months(p.term_months)}</span></div>
                  <input type="range" min={3} max={84} step={1} value={p.term_months} onChange={(e) => set({ term_months: Number(e.target.value) })} aria-label={t("Срок кредита")} />
                  <div className="row between small muted"><span>{months(3)}</span><span>{months(84)}</span></div>
                </div>
              </div>
              <div className="grid g2">
                <div className="stack"><h3>{t("Нужен залог?")}</h3><YesNo value={p.has_collateral} onChange={(v) => set({ has_collateral: v })} no={t("Без залога")} yes={t("С залогом")} /></div>
                <div className="stack"><h3>{t("Нужна отсрочка платежа?")}</h3><YesNo value={p.deferral} onChange={(v) => set({ deferral: v })} no={t("Нет")} yes={t("Да")} /></div>
              </div>
            </>
          )}

          {step === 1 && (
            <div className="stack">
              <h3>{t("О компании")}</h3>
              <p className="muted">{t("Сведения подтянуты из ЕГРЮЛ — заполнять ничего не нужно. Возраст бизнеса учитывается в подборе.")}</p>
              <dl className="kv">
                <dt>{t("Компания")}</dt><dd>{company?.name}</dd>
                <dt>{t("ИНН")}</dt><dd>{company?.inn}</dd>
                <dt>{t("ОКВЭД")}</dt><dd>{company?.okved} {company?.okved_name}</dd>
                <dt>{t("Регион")}</dt><dd>{company?.region ?? "—"}</dd>
                <dt>{t("Дата регистрации")}</dt><dd>{date(company?.registered_at)}</dd>
                <dt>{t("Возраст бизнеса")}</dt><dd>{months(p.business_age_months)}</dd>
              </dl>
            </div>
          )}

          {step === 2 && (
            <div className="stack">
              <h3>{t("Финансовые данные")}</h3>
              <p className="muted">{t("Средняя выручка в месяц нужна, чтобы проверить, что платёж будет комфортным. Можно пропустить.")}</p>
              <label className="field" style={{ maxWidth: 420 }}>
                <span>{t("Выручка в месяц, ₽")}</span>
                <MoneyInput big value={p.monthly_revenue ?? 0} onChange={(v) => set({ monthly_revenue: v || null })} />
              </label>
              {p.monthly_revenue ? (
                <div className="alert info">{t("Комфортный платёж — до {0} в месяц (30% выручки).", money(p.monthly_revenue * 0.3))}</div>
              ) : null}
            </div>
          )}

          {step === 3 && (
            <div className="stack lg">
              <div className="stack"><h3>{t("Что для вас важнее всего?")}</h3><PriorityPick value={p.priority} onChange={(v) => set({ priority: v })} /></div>
              <label className="check"><input type="checkbox" checked={reset} onChange={(e) => setReset(e.target.checked)} />
                {t("Показать заново и пропущенные предложения")}</label>
            </div>
          )}

          <ErrorBox error={error} />
          <div className="row between">
            <button className="btn ghost" disabled={step === 0} onClick={() => setStep(step - 1)}><ChevronLeft size={18} />{t("Назад")}</button>
            {step < STEPS.length - 1
              ? <button className="btn primary lg" onClick={() => setStep(step + 1)}>{t("Продолжить")}<ChevronRight size={18} /></button>
              : <button className="btn primary lg" onClick={save}>{t("Показать предложения")}<ChevronRight size={18} /></button>}
          </div>
        </div>

        <div className="stack">
          <div className="card current-pick">
            <h3 style={{ marginBottom: 6 }}>{t("Текущий подбор")}</h3>
            {[
              { label: t("Цель"), value: purpose?.label ?? p.purpose, s: 0, icon: purpose?.icon ?? Ellipsis },
              { label: t("Сумма"), value: money(p.amount), s: 0, icon: Wallet },
              { label: t("Срок"), value: months(p.term_months), s: 0, icon: Repeat },
              { label: t("Залог"), value: p.has_collateral ? t("С залогом") : t("Без залога"), s: 0, icon: Building2 },
              { label: t("Важнее всего"), value: priority?.label ?? "", s: 3, icon: priority?.icon ?? Check },
            ].map((r) => (
              <div className="cp" key={r.label}>
                <span className="avatar-ring"><r.icon size={18} /></span>
                <div><small>{r.label}</small><b>{r.value}</b></div>
                <button className="ed" aria-label={t("Изменить")} onClick={() => setStep(r.s)}><Pencil size={16} /></button>
              </div>
            ))}
            <button className="btn ghost block mt" onClick={() => { setP({ ...p, ...DEFAULTS } as MatchProfile); setStep(0); }}><RotateCcw size={16} />{t("Сбросить параметры")}</button>
          </div>
          <div className="card helper-panel">
            <div className="hp-art" style={{ height: 130 }}><img src="/brand/alfik-jump.webp" alt="" style={{ width: 150 }} /></div>
            <h3>{t("Ваш помощник")}</h3>
            <p className="muted small">{t("Я помогу подобрать кредит под ваши задачи — без лишних документов и долгих ожиданий.")}</p>
          </div>
          <div className="card stack">
            <div className="row between"><h3>{t("Советы")}</h3><span className="muted small">{tip + 1} / {TIPS.length}</span></div>
            <p className="text-2">{TIPS[tip]}</p>
            <div className="row">
              <button className="round-btn" style={{ width: 40, height: 40 }} aria-label={t("Предыдущий совет")} onClick={() => setTip((tip + TIPS.length - 1) % TIPS.length)}><ChevronLeft size={18} /></button>
              <button className="round-btn" style={{ width: 40, height: 40 }} aria-label={t("Следующий совет")} onClick={() => setTip((tip + 1) % TIPS.length)}><ChevronRight size={18} /></button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
