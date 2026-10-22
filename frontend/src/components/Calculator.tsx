import { useEffect, useState } from "react";
import { api } from "../api";
import { money, months } from "../format";
import type { Estimate, Product } from "../types";
import { AlfikSay, MoneyInput } from "./ui";
import { t } from "../i18n";

interface Props {
  product: Product;
  amount: number;
  term: number;
  hasCollateral?: boolean;
  onChange: (amount: number, term: number) => void;
}

export default function Calculator({ product, amount, term, hasCollateral, onChange }: Props) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [tooHigh, setTooHigh] = useState(false);
  const [comfort, setComfort] = useState(0);
  const [alts, setAlts] = useState<Estimate[] | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<Estimate>("/api/calculator", {
        body: { product_code: product.code, amount, term_months: term, has_collateral: !!hasCollateral },
      }).then(setEst).catch(() => setEst(null));
    }, 200);
    return () => clearTimeout(t);
  }, [product.code, amount, term, hasCollateral]);

  async function findAlternatives() {
    const r = await api<{ alternatives: Estimate[] }>("/api/calculator", {
      body: { product_code: product.code, amount, term_months: term, has_collateral: !!hasCollateral, comfortable_payment: comfort },
    });
    setAlts(r.alternatives);
  }

  const termFixed = product.min_term === product.max_term;
  const step = product.max_amount > 10_000_000 ? 100_000 : 10_000;

  return (
    <div className="stack lg">
      <div className="grid" style={{ gridTemplateColumns: "1fr 260px" }}>
        <div className="card flat">
          <div className="row between">
            <h3>{t("Сумма:")} {money(amount)}</h3>
            <span className="badge ok">{t("до")} {money(product.max_amount)}</span>
          </div>
          <p className="small muted" style={{ marginTop: 4 }}>{t("Двигайте ползунок или введите сумму")}</p>
          <div className="row mt" style={{ flexWrap: "nowrap" }}>
            <input type="range" min={product.min_amount} max={product.max_amount} step={step} value={Math.min(Math.max(amount, product.min_amount), product.max_amount)}
              onChange={(e) => onChange(Number(e.target.value), term)} />
            <div style={{ width: 170 }}><MoneyInput value={amount} onChange={(v) => onChange(v, term)} /></div>
          </div>
          {!termFixed && (
            <>
              <h3 className="mt">{t("Срок:")} {months(term)}</h3>
              <input type="range" min={product.min_term} max={product.max_term} step={1} value={term}
                onChange={(e) => onChange(amount, Number(e.target.value))} />
              <div className="row between small muted"><span>{product.min_term}  {t("мес.")}</span><span>{product.max_term}  {t("мес.")}</span></div>
            </>
          )}
          {termFixed && <p className="small muted mt">{t("Овердрафт выдаётся на")} {product.max_term}  {t("месяцев с возобновляемым лимитом.")}</p>}
        </div>
        <div className="stat accent" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div className="label">{product.revolving ? t("Проценты в месяц при полном использовании") : t("Ежемесячный платёж")}</div>
          <div className="value" style={{ fontSize: 34 }}>{money(est?.monthly_payment)}</div>
          <div className="label" style={{ marginTop: 8 }}>{t("ставка от")} {est?.rate ?? product.base_rate}{t("% годовых")}</div>
        </div>
      </div>
      <div className="grid g3">
        <div className="stat"><div className="label">{t("Ставка")}</div><div className="value">{est?.rate ?? product.base_rate}%</div></div>
        <div className="stat"><div className="label">{t("Переплата")}</div><div className="value">{money(est?.total_interest)}</div></div>
        <div className="stat"><div className="label">{t("Всего к возврату")}</div><div className="value">{money(est?.total_repayment)}</div></div>
      </div>
      {!product.revolving && (
        <div>
          {!tooHigh ? (
            <button className="link" onClick={() => { setTooHigh(true); setComfort(Math.round((est?.monthly_payment ?? 0) * 0.7 / 1000) * 1000); }}>
              
              {t("Платёж слишком высокий для меня")}
            </button>
          ) : (
            <div className="card flat stack">
              <AlfikSay size="sm" pose="notes" soft>{t("Скажите, какой платёж для бизнеса комфортен, — я подберу сумму и срок.")}</AlfikSay>
              <div className="row">
                <div style={{ width: 220 }}><MoneyInput value={comfort} onChange={setComfort} placeholder={t("Комфортный платёж")} /></div>
                <button className="btn dark" onClick={findAlternatives} disabled={!comfort}>{t("Подобрать условия")}</button>
              </div>
              {alts && alts.length === 0 && <p className="muted">{t("При таком платеже этот продукт не подойдёт — попробуйте увеличить платёж или выбрать другой продукт.")}</p>}
              {alts && alts.length > 0 && (
                <div className="grid g3">
                  {alts.map((a) => (
                    <button key={a.label} className="offer-card" onClick={() => { onChange(a.amount, a.term_months); setTooHigh(false); setAlts(null); }}>
                      <div className="small muted">{a.label}</div>
                      <div className="big">{money(a.monthly_payment)}<span className="small muted">  {t("/ мес")}</span></div>
                      <div className="small">{money(a.amount)}  {t("на")} {months(a.term_months)}</div>
                      <div className="small muted">{t("переплата")} {money(a.total_interest)}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
