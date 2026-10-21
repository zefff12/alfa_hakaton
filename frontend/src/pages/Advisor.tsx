import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import Calculator from "../components/Calculator";
import { AlfikSay, ErrorBox, Loader, MoneyInput, useCatalog } from "../components/ui";
import { money } from "../format";
import type { Application } from "../types";

const STEPS = ["purpose", "amount", "term", "collateral", "urgency"] as const;
const AMOUNTS = [300_000, 1_000_000, 3_000_000, 5_000_000, 15_000_000];
const TERMS = [6, 12, 24, 36, 60];

export default function Advisor() {
  const catalog = useCatalog();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [step, setStep] = useState(params.get("purpose") ? 1 : 0);
  const [need, setNeed] = useState({
    purpose: params.get("purpose") ?? "", amount: 1_000_000, term_months: 12, has_collateral: false,
    urgency: "normal", business_age_months: 24,
  });
  const [result, setResult] = useState<any>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [calc, setCalc] = useState({ amount: 1_000_000, term: 12 });
  const [error, setError] = useState<any>(null);

  useEffect(() => {
    if (params.get("calc") && catalog && !result) {
      setChosen("EXPRESS");
      setResult({ items: [], explanation: "" });
    }
  }, [catalog, params, result]);

  async function finish(n = need) {
    const r = await api("/api/advisor/recommend", { body: n });
    setResult(r);
    const best = r.best ?? r.items[0].product.code;
    setChosen(best);
    const p = catalog!.products.find((x) => x.code === best)!;
    setCalc({ amount: Math.min(Math.max(n.amount, p.min_amount), p.max_amount), term: Math.min(Math.max(n.term_months, p.min_term), p.max_term) });
  }

  async function apply() {
    setError(null);
    try {
      const app = await api<Application>("/api/applications", {
        body: { product_code: chosen, purpose: need.purpose || "other", amount: calc.amount, term_months: calc.term,
                form_data: { has_collateral: need.has_collateral } },
      });
      nav(`/applications/${app.id}`);
    } catch (e) { setError(e); }
  }

  if (!catalog) return <Loader />;
  const product = catalog.products.find((p) => p.code === chosen);
  const next = (patch: Partial<typeof need>) => {
    const n = { ...need, ...patch };
    setNeed(n);
    if (step < STEPS.length - 1) setStep(step + 1);
    else finish(n);
  };

  const questions: Record<string, { q: string; body: React.ReactNode }> = {
    purpose: {
      q: "На что бизнесу нужны деньги?",
      body: (
        <div className="chips">
          {catalog.purposes.map((p) => (
            <button key={p.code} className={`chip ${need.purpose === p.code ? "on" : ""}`} onClick={() => next({ purpose: p.code })}>{p.label}</button>
          ))}
        </div>
      ),
    },
    amount: {
      q: "Сколько примерно нужно?",
      body: (
        <div className="stack">
          <div className="chips">
            {AMOUNTS.map((a) => <button key={a} className={`chip ${need.amount === a ? "on" : ""}`} onClick={() => next({ amount: a })}>{money(a)}</button>)}
          </div>
          <div className="row">
            <div style={{ width: 240 }}><MoneyInput value={need.amount} onChange={(v) => setNeed({ ...need, amount: v })} /></div>
            <button className="btn dark" onClick={() => next({})}>Дальше</button>
          </div>
        </div>
      ),
    },
    term: {
      q: "На какой срок? Чем дольше — тем ниже платёж, но больше переплата.",
      body: (
        <div className="chips">
          {TERMS.map((t) => <button key={t} className={`chip ${need.term_months === t ? "on" : ""}`} onClick={() => next({ term_months: t })}>{t} мес.</button>)}
        </div>
      ),
    },
    collateral: {
      q: "Есть ли залог — недвижимость, транспорт или оборудование (в т.ч. то, что покупаете)?",
      body: (
        <div className="chips">
          <button className="chip" onClick={() => next({ has_collateral: true })}>Да, есть</button>
          <button className="chip" onClick={() => next({ has_collateral: false })}>Нет залога</button>
        </div>
      ),
    },
    urgency: {
      q: "Насколько срочно нужны деньги?",
      body: (
        <div className="chips">
          <button className="chip" onClick={() => next({ urgency: "urgent" })}>Срочно, в течение дня</button>
          <button className="chip" onClick={() => next({ urgency: "normal" })}>Могу подождать пару дней</button>
        </div>
      ),
    },
  };

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>Подбор кредита</h1>
          <p>Альфик задаст 5 вопросов и объяснит, какой продукт подходит и почему</p>
        </div>
        {result && <button className="btn ghost" onClick={() => { setResult(null); setStep(0); }}>Начать заново</button>}
      </div>

      {!result && (
        <div className="card stack lg">
          <div className="wizard-steps">
            {STEPS.map((s, i) => (
              <button key={s} className={i === step ? "on" : i < step ? "done" : ""} onClick={() => i < step && setStep(i)}>
                {i + 1}. {["Цель", "Сумма", "Срок", "Залог", "Срочность"][i]}
              </button>
            ))}
          </div>
          <AlfikSay pose="notes">{questions[STEPS[step]].q}</AlfikSay>
          <div style={{ paddingLeft: 106 }}>{questions[STEPS[step]].body}</div>
        </div>
      )}

      {result && result.items.length > 0 && (
        <>
          <AlfikSay pose="wave">{result.explanation}</AlfikSay>
          <div className="grid g2">
            {result.items.map((it: any) => (
              <button key={it.product.code} className={`product-card ${chosen === it.product.code ? "on" : ""}`}
                onClick={() => {
                  setChosen(it.product.code);
                  setCalc({ amount: Math.min(Math.max(need.amount, it.product.min_amount), it.product.max_amount),
                            term: Math.min(Math.max(need.term_months, it.product.min_term), it.product.max_term) });
                }}>
                <div className="row between">
                  <b>{it.product.name}</b>
                  {result.best === it.product.code && <span className="badge red">Лучший выбор</span>}
                </div>
                <small>{it.product.short} · от {it.product.base_rate}% · {it.product.decision_time}</small>
                <div className="row mt" style={{ gap: 8 }}>
                  <div className="fit-bar" style={{ flex: 1 }}><div style={{ width: `${it.fit_score}%` }} /></div>
                  <span className="small"><b>{it.fit_score}%</b> совпадение</span>
                </div>
                <div className="small mt" style={{ lineHeight: 1.6 }}>
                  {it.pros.map((p: string) => <div key={p} className="pos">✓ {p}</div>)}
                  {it.cons.map((c: string) => <div key={c} className="neg">✕ {c}</div>)}
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      {result && product && (
        <div className="card stack lg">
          <div className="row between">
            <div>
              <h2>{product.name}</h2>
              <p className="muted">{product.description}</p>
            </div>
            {result.items.length === 0 && (
              <select className="input" style={{ width: 280 }} value={chosen ?? ""} onChange={(e) => setChosen(e.target.value)}>
                {catalog.products.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
              </select>
            )}
          </div>
          <Calculator product={product} amount={calc.amount} term={calc.term} hasCollateral={need.has_collateral}
            onChange={(amount, term) => setCalc({ amount, term })} />
          <ErrorBox error={error} />
          <div className="row">
            <button className="btn primary" onClick={apply}>Оформить заявку на {money(calc.amount)}</button>
            <button className="btn ghost" onClick={() => nav(`/precheck?product=${product.code}&amount=${calc.amount}&term=${calc.term}`)}>
              Сначала узнать шансы
            </button>
          </div>
          <p className="small muted">Расчёт предварительный: итоговая ставка зависит от оценки банка. Условия в прототипе синтетические.</p>
        </div>
      )}
    </div>
  );
}
