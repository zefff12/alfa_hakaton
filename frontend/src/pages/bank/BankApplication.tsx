import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getToken } from "../../api";
import { ErrorBox, FactorList, Field, Loader, MoneyInput, StatusBadge, useCatalog } from "../../components/ui";
import { date, dateTime, money, months } from "../../format";
import type { Application } from "../../types";

function DecisionPanel({ app, onDone }: { app: Application; onDone: (a: Application) => void }) {
  const catalog = useCatalog();
  const rec = app.decision?.recommendation ?? {};
  const [outcome, setOutcome] = useState<"APPROVED" | "COUNTER_OFFER" | "INFO_REQUESTED" | "REJECTED">("APPROVED");
  const [amount, setAmount] = useState<number>(rec.amount ?? app.amount ?? 0);
  const [term, setTerm] = useState<number>(rec.term_months ?? app.term_months ?? 12);
  const [rate, setRate] = useState<number>(rec.rate ?? 22);
  const [docs, setDocs] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<any>(null);

  async function send() {
    setError(null);
    try {
      onDone(await api<Application>(`/api/bank/applications/${app.id}/decision`, {
        body: { version: app.version, outcome, amount, term_months: term, rate, requested_documents: docs, reason, comment },
      }));
    } catch (e) { setError(e); }
  }

  return (
    <div className="card stack" style={{ border: "2px solid var(--red)" }}>
      <h3>Решение специалиста</h3>
      {rec.limit != null && (
        <div className="alert info small">Рекомендация движка: лимит {money(rec.limit)}, ставка {rec.rate}%, сумма к одобрению {money(rec.amount)}</div>
      )}
      <div className="pill-tabs">
        {([["APPROVED", "Одобрить"], ["COUNTER_OFFER", "Изменить условия"], ["INFO_REQUESTED", "Запросить документы"], ["REJECTED", "Отказать"]] as const).map(([k, l]) => (
          <button key={k} className={outcome === k ? "on" : ""} onClick={() => setOutcome(k)}>{l}</button>
        ))}
      </div>
      {(outcome === "APPROVED" || outcome === "COUNTER_OFFER") && (
        <div className="grid g3">
          <Field label="Сумма"><MoneyInput value={amount} onChange={setAmount} /></Field>
          <Field label="Срок, мес."><input className="input" type="number" value={term} onChange={(e) => setTerm(Number(e.target.value))} /></Field>
          <Field label="Ставка, %"><input className="input" type="number" step="0.1" value={rate} onChange={(e) => setRate(Number(e.target.value))} /></Field>
        </div>
      )}
      {outcome === "INFO_REQUESTED" && (
        <div className="chips">
          {catalog?.document_types.map((d) => (
            <button key={d.code} className={`chip ${docs.includes(d.code) ? "on" : ""}`}
              onClick={() => setDocs(docs.includes(d.code) ? docs.filter((x) => x !== d.code) : [...docs, d.code])}>{d.label}</button>
          ))}
        </div>
      )}
      {outcome === "REJECTED" && (
        <Field label="Причина для клиента (будет показана в кабинете)">
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: недостаточная платёжеспособность для запрошенной суммы" />
        </Field>
      )}
      <Field label="Комментарий"><textarea className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      <ErrorBox error={error} />
      <button className="btn primary" onClick={send}>Зафиксировать решение</button>
    </div>
  );
}

function Compare({ app }: { app: Application }) {
  const fd = app.form_data;
  const fns = app.enrichment?.sources?.fns;
  const bki = app.enrichment?.sources?.bki;
  const rows: [string, string, string, boolean][] = [
    ["Выручка в год", money((fd.monthly_revenue ?? 0) * 12), fns ? money(fns.annual_revenue) : "—",
      !!fns && Math.abs((fd.monthly_revenue ?? 0) * 12 - fns.annual_revenue) / fns.annual_revenue > 0.4],
    ["Платежи по кредитам в мес.", money(fd.existing_payments ?? 0), bki ? money(bki.total_monthly_payments) : "—",
      !!bki && bki.total_monthly_payments > (fd.existing_payments ?? 0) * 1.2],
  ];
  return (
    <table className="tbl compare">
      <thead><tr><th>Показатель</th><th>Со слов клиента</th><th>Из источников</th></tr></thead>
      <tbody>{rows.map(([n, a, b, diff]) => <tr key={n}><td>{n}</td><td>{a}</td><td className={diff ? "diff" : ""}>{b}{diff ? " ⚠" : ""}</td></tr>)}</tbody>
    </table>
  );
}

export default function BankApplication() {
  const { id } = useParams();
  const [app, setApp] = useState<Application | null>(null);
  const load = useCallback(() => api<Application>(`/api/bank/applications/${id}`).then(setApp), [id]);
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, [load]);
  if (!app) return <Loader />;

  const src = app.enrichment?.sources ?? {};
  const sc = app.scoring;
  const reviewDoc = async (docId: number, status: string) => setApp(await api(`/api/bank/documents/${docId}/review?status=${status}`, { method: "POST" }));

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <div className="row"><h1>{app.number}</h1><StatusBadge status={app.status} label={app.status_label} /></div>
          <p>{app.company.name} · ИНН {app.company.inn} · заявитель {app.applicant?.full_name} ({app.applicant?.position})</p>
        </div>
        <div className="row">
          {app.status === "MANUAL_REVIEW" && (
            <button className="btn dark sm" onClick={async () => setApp(await api(`/api/bank/applications/${app.id}/assign`, { body: {} }))}>Взять в работу</button>
          )}
          <Link to="/bank" className="btn ghost sm">← Очередь</Link>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)" }}>
        <div className="stack lg">
          <div className="card">
            <h3>Запрос клиента</h3>
            <dl className="kv mt">
              <dt>Продукт</dt><dd>{app.product_name}</dd>
              <dt>Сумма / срок</dt><dd>{money(app.amount)} / {months(app.term_months)}</dd>
              <dt>Цель</dt><dd>{app.purpose_label}{app.purpose_comment ? ` — ${app.purpose_comment}` : ""}</dd>
              <dt>Залог</dt><dd>{app.has_collateral ? app.collateral_description || "да" : "нет"}</dd>
              <dt>Выручка / расходы</dt><dd>{money(app.form_data.monthly_revenue)} / {money(app.form_data.monthly_expenses)} в мес.</dd>
              <dt>Согласие БКИ</dt><dd>{app.consents.bki ? `да, ${app.consents.bki_consent_id}` : "нет"}</dd>
            </dl>
            <div className="sep" />
            <Compare app={app} />
          </div>

          {sc && (
            <div className="card">
              <div className="row between">
                <h3>Скоринг ({sc.model_version})</h3>
                <div className="row"><span className="badge neutral">Класс {sc.risk_class} · {sc.risk_label}</span><b style={{ fontSize: 24 }}>{sc.score}</b></div>
              </div>
              <p className="small muted">База {sc.base_score} ± вклад факторов · PD ≈ {(sc.pd * 100).toFixed(1)}% · долговая нагрузка {sc.debt_burden == null ? "—" : `${Math.round(sc.debt_burden * 100)}%`}</p>
              <div className="mt"><FactorList factors={sc.factors} /></div>
            </div>
          )}

          {app.decision?.rules && (
            <div className="card">
              <h3>Кредитная логика ({app.decision.engine_version})</h3>
              <table className="tbl mt">
                <tbody>
                  {app.decision.rules.map((r: any) => (
                    <tr key={r.code}>
                      <td>{r.result === "pass" ? "✅" : r.result === "warn" ? "⚠️" : "⛔"}</td>
                      <td><b>{r.name}</b><div className="small muted">{r.detail}</div></td>
                      <td className="small muted">{r.code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt small">Итог движка: <b>{app.decision.outcome}</b> — {app.decision.reasons?.map((r: any) => r.text).join("; ")}</div>
              {app.decision.manual && <div className="alert warn mt small">Ручное решение: {app.decision.manual.by_name}, {dateTime(app.decision.manual.at)}. {app.decision.manual.comment}</div>}
            </div>
          )}
        </div>

        <div className="stack lg">
          {app.status === "MANUAL_REVIEW" && <DecisionPanel app={app} onDone={setApp} />}

          <div className="card stack">
            <h3>Внешние источники</h3>
            {app.enrichment?.errors?.map((e: any) => <div key={e.source} className="alert warn small">{e.service}: {e.message}</div>)}
            {src.egrul && (
              <details open>
                <summary>ЕГРЮЛ / ЕГРИП</summary>
                <dl className="kv mt small">
                  <dt>Статус</dt><dd>{src.egrul.status}</dd>
                  <dt>Регистрация</dt><dd>{date(src.egrul.registered_at)}</dd>
                  <dt>ОКВЭД</dt><dd>{src.egrul.okved} {src.egrul.okved_name}</dd>
                  <dt>Руководитель</dt><dd>{src.egrul.director}</dd>
                  <dt>Массовый адрес</dt><dd>{src.egrul.mass_address ? "да ⚠" : "нет"}</dd>
                </dl>
              </details>
            )}
            {src.fns && (
              <details open>
                <summary>ФНС «Прозрачный бизнес»</summary>
                <dl className="kv mt small">
                  <dt>Выручка за {src.fns.revenue_year}</dt><dd>{money(src.fns.annual_revenue)}</dd>
                  <dt>Налоговый долг</dt><dd>{money(src.fns.tax_arrears)}</dd>
                  <dt>Сотрудников</dt><dd>{src.fns.employees}</dd>
                  <dt>Режим</dt><dd>{src.fns.tax_regime}</dd>
                </dl>
              </details>
            )}
            {src.bki && (
              <details open>
                <summary>БКИ</summary>
                <dl className="kv mt small">
                  <dt>Кредитная история</dt><dd>{src.bki.credit_history_months} мес.</dd>
                  <dt>Макс. просрочка 12 мес.</dt><dd>{src.bki.max_delinquency_days_12m} дн.</dd>
                  <dt>Платежи в месяц</dt><dd>{money(src.bki.total_monthly_payments)}</dd>
                  <dt>Балл БКИ</dt><dd>{src.bki.bki_score}</dd>
                </dl>
                {src.bki.active_loans.map((l: any, i: number) => (
                  <div key={i} className="small muted">• {l.bank}: {l.type}, остаток {money(l.balance)}, платёж {money(l.monthly_payment)}</div>
                ))}
              </details>
            )}
            {!app.enrichment && <p className="muted small">Ещё не запрашивались</p>}
          </div>

          <div className="card stack">
            <h3>Документы</h3>
            {app.documents.length === 0 && <p className="muted small">Нет документов</p>}
            {app.documents.map((d) => (
              <div key={d.id} className="row between small">
                <div>
                  <b>{d.label}</b>
                  <div className="muted">{d.filename} · <a href="#" onClick={async (e) => {
                    e.preventDefault();
                    const res = await fetch(`/api/documents/${d.id}/download`, { headers: { Authorization: `Bearer ${getToken()}` } });
                    const url = URL.createObjectURL(await res.blob());
                    window.open(url, "_blank");
                  }}>открыть</a></div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <span className={`badge ${d.status === "ACCEPTED" ? "ok" : d.status === "REJECTED" ? "bad" : "neutral"}`}>{d.status}</span>
                  <button className="btn ghost sm" onClick={() => reviewDoc(d.id, "ACCEPTED")}>✓</button>
                  <button className="btn ghost sm" onClick={() => reviewDoc(d.id, "REJECTED")}>✕</button>
                </div>
              </div>
            ))}
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 14 }}>Аудит</h3>
            <div className="timeline">
              {[...app.timeline].reverse().map((e) => (
                <div key={e.id} className="tl-item">
                  <div className={`tl-dot ${e.actor_type}`} />
                  <div>
                    <div className="what small"><b>{e.event_type}</b> {e.from_status ? `${e.from_status} → ${e.to_status}` : ""}</div>
                    <div className="small">{e.message}</div>
                    <div className="when">{dateTime(e.created_at)} · {e.actor_type}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
