import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { AlfikSay, ErrorBox, FactorList, Field, Gauge, Loader, MoneyInput, useCatalog } from "../components/ui";
import { money, months } from "../format";
import type { Application } from "../types";

const DELINQ = [
  { v: "none", l: "Просрочек не было" },
  { v: "minor", l: "Были короткие, до 30 дней" },
  { v: "serious", l: "Были долгие, больше месяца" },
  { v: "current", l: "Есть просрочка сейчас" },
];

export default function Precheck() {
  const catalog = useCatalog();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({
    product_code: params.get("product") ?? "EXPRESS",
    amount: Number(params.get("amount") ?? 1_000_000),
    term_months: Number(params.get("term") ?? 12),
    business_age_months: 24,
    monthly_revenue: 0,
    monthly_expenses: 0,
    existing_monthly_payments: 0,
    delinquency: "none",
    tax_arrears: false,
    has_collateral: false,
  });
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  if (!catalog) return <Loader />;
  const product = catalog.products.find((p) => p.code === form.product_code)!;
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });

  async function check() {
    setBusy(true);
    setError(null);
    try {
      setRes(await api("/api/precheck", { body: form }));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  async function toApplication(amount = form.amount, term = form.term_months) {
    const app = await api<Application>("/api/applications", {
      body: {
        product_code: form.product_code, purpose: product.purposes[0], amount, term_months: term, precheck: res,
        form_data: { monthly_revenue: form.monthly_revenue, monthly_expenses: form.monthly_expenses,
                     existing_payments: form.existing_monthly_payments, has_collateral: form.has_collateral },
      },
    });
    nav(`/applications/${app.id}`);
  }

  const positives = res?.factors.filter((f: any) => f.points > 0) ?? [];
  const negatives = res?.factors.filter((f: any) => f.points < 0) ?? [];

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>Каковы мои шансы на одобрение?</h1>
          <p>Ответьте на несколько вопросов о бизнесе — Альфик покажет готовность к подаче и что можно улучшить</p>
        </div>
      </div>

      {res && (
        <div className="card stack lg">
          <div className="row" style={{ alignItems: "center", gap: 28 }}>
            <Gauge value={res.readiness} label="готовность" />
            <div className="stack" style={{ flex: 1, minWidth: 280 }}>
              <h2>{res.title}</h2>
              <p className="muted">
                Ориентировочно: ставка от {res.estimated_rate}%, платёж ~{money(res.estimated_payment)} в месяц
                {res.estimated_limit ? `, комфортная сумма до ${money(res.estimated_limit)}` : ""}.
              </p>
              {res.blockers.length > 0 && <div className="alert bad">{res.blockers.map((b: string) => <div key={b}>⛔ {b}</div>)}</div>}
              {res.suggestion && <div className="alert info">💡 {res.suggestion.text}</div>}
            </div>
          </div>
          <div className="alert warn">⚠️ {res.disclaimer}</div>
          <div className="stack">
            <div className="card flat">
              <h3 className="pos">Что помогает ({positives.length})</h3>
              <FactorList factors={positives} />
            </div>
            <div className="card flat">
              <h3 className="neg">Что мешает ({negatives.length})</h3>
              {negatives.length ? <FactorList factors={negatives} /> : <p className="muted mt">Явных негативных факторов нет 🎉</p>}
            </div>
          </div>
          {res.tips.length > 0 && (
            <AlfikSay pose="notes" soft>
              Мои советы, чтобы повысить шансы:
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{res.tips.map((t: string) => <li key={t}>{t}</li>)}</ul>
            </AlfikSay>
          )}
          <div className="row">
            <button className="btn primary" onClick={() => toApplication()} disabled={res.blockers.length > 0}>
              Оформить заявку с этими данными
            </button>
            {res.suggestion?.longer_term && (
              <button className="btn soft" onClick={() => toApplication(form.amount, res.suggestion.longer_term)}>
                Оформить на {months(res.suggestion.longer_term)}
              </button>
            )}
            {res.suggestion?.comfortable_amount > 0 && (
              <button className="btn soft" onClick={() => toApplication(res.suggestion.comfortable_amount)}>
                Оформить на {money(res.suggestion.comfortable_amount)}
              </button>
            )}
            <button className="btn ghost" onClick={() => setRes(null)}>Изменить ответы</button>
          </div>
          <p className="small muted">Ответы перенесутся в заявку — вводить их повторно не придётся.</p>
        </div>
      )}

      {!res && (
        <div className="card stack lg">
          <AlfikSay pose="notes">
            Это займёт минуту. Я не запрашиваю кредитную историю и ничего не отправляю в банк — оценка только по вашим ответам.
          </AlfikSay>
          <div className="grid g3">
            <Field label="Продукт">
              <select className="input" value={form.product_code} onChange={(e) => set({ product_code: e.target.value })}>
                {catalog.products.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Сумма кредита" hint={`от ${money(product.min_amount)} до ${money(product.max_amount)}`}>
              <MoneyInput value={form.amount} onChange={(v) => set({ amount: v })} />
            </Field>
            <Field label="Срок, мес." hint={`от ${product.min_term} до ${product.max_term}`}>
              <input className="input" type="number" min={product.min_term} max={product.max_term} value={form.term_months}
                onChange={(e) => set({ term_months: Number(e.target.value) })} />
            </Field>
            <Field label="Сколько месяцев работает бизнес?">
              <input className="input" type="number" min={0} value={form.business_age_months}
                onChange={(e) => set({ business_age_months: Number(e.target.value) })} />
            </Field>
            <Field label="Средняя выручка в месяц" hint="за последние 6 месяцев">
              <MoneyInput value={form.monthly_revenue} onChange={(v) => set({ monthly_revenue: v })} />
            </Field>
            <Field label="Средние расходы в месяц" hint="аренда, зарплаты, закупки, налоги">
              <MoneyInput value={form.monthly_expenses} onChange={(v) => set({ monthly_expenses: v })} />
            </Field>
            <Field label="Платежи по текущим кредитам в месяц" hint="0, если кредитов нет">
              <MoneyInput value={form.existing_monthly_payments} onChange={(v) => set({ existing_monthly_payments: v })} />
            </Field>
          </div>
          <div className="grid g2">
            <div className="field">
              <span>Были ли просрочки по кредитам за последний год?</span>
              <div className="chips">
                {DELINQ.map((d) => <button key={d.v} className={`chip ${form.delinquency === d.v ? "on" : ""}`} onClick={() => set({ delinquency: d.v })}>{d.l}</button>)}
              </div>
            </div>
            <div className="stack">
              <label className="check"><input type="checkbox" checked={form.tax_arrears} onChange={(e) => set({ tax_arrears: e.target.checked })} />Есть задолженность по налогам</label>
              <label className="check"><input type="checkbox" checked={form.has_collateral} onChange={(e) => set({ has_collateral: e.target.checked })} />Есть залог (недвижимость, транспорт, оборудование)</label>
            </div>
          </div>
          <ErrorBox error={error} />
          <div><button className="btn primary" onClick={check} disabled={busy || !form.monthly_revenue}>Оценить шансы</button></div>
        </div>
      )}
    </div>
  );
}
