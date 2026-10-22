import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import DocUpload from "../components/DocUpload";
import DraftForm from "../components/DraftForm";
import StatementCard, { SampleStatements } from "../components/StatementCard";
import { AlfikSay, ErrorBox, Loader, StatusBadge, Track } from "../components/ui";
import { date, dateTime, money, months } from "../format";
import type { Application } from "../types";
import { PROCESSING } from "../types";
import { t } from "../i18n";

const POLL_STATUSES = [...PROCESSING, "MANUAL_REVIEW"];

const SUBSTEPS = [
  { key: "SUBMITTED", label: t("Заявка принята банком") },
  { key: "DATA_CHECK", label: t("Проверка полноты и корректности данных") },
  { key: "ENRICHMENT", label: t("Сведения из ЕГРЮЛ, ФНС «Прозрачный бизнес» и БКИ") },
  { key: "SCORING", label: t("Оценка риска и подбор условий") },
];

function Processing({ app }: { app: Application }) {
  const order = SUBSTEPS.map((s) => s.key);
  const idx = order.indexOf(app.status);
  const manual = app.status === "MANUAL_REVIEW";
  const integrationErrors = app.timeline.filter((e) => e.event_type === "INTEGRATION_ERROR");
  return (
    <div className="substeps">
      {SUBSTEPS.map((s, i) => {
        const state = manual ? "done" : i < idx ? "done" : i === idx ? "run" : "wait";
        const failed = s.key === "ENRICHMENT" && integrationErrors.length > 0;
        return (
          <div key={s.key} className={`substep ${failed ? "fail" : state}`}>
            <span className="st">{failed ? "!" : state === "done" ? "✓" : state === "wait" ? i + 1 : ""}</span>
            {s.label}
            {failed && <span className="small muted">{t("— часть источников недоступна, заявку проверит специалист")}</span>}
          </div>
        );
      })}
      {manual && (
        <div className="substep run"><span className="st" />{t("Рассмотрение кредитным специалистом")}</div>
      )}
    </div>
  );
}

function OfferBlock({ app, onChange }: { app: Application; onChange: (a: Application) => void }) {
  const [opt, setOpt] = useState(app.offer?.options[0]?.id ?? "");
  const [error, setError] = useState<any>(null);
  const offer = app.offer!;
  const act = async (path: string, body: object) => {
    setError(null);
    try { onChange(await api<Application>(`/api/applications/${app.id}/${path}`, { body: { version: app.version, ...body } })); }
    catch (e) { setError(e); }
  };
  return (
    <div className="card stack lg">
      <div className="row between">
        <h2>{app.status === "APPROVED" ? t("Ваше предложение") : t("Банк предлагает другие условия")}</h2>
        <span className="small muted">{t("действует до")} {date(offer.valid_until)}</span>
      </div>
      {app.status === "COUNTER_OFFER" && app.decision?.reasons?.[0] && <div className="alert info">💡 {app.decision.reasons[0].text}</div>}
      <p className="muted">{offer.product_name}</p>
      <div className="grid g2">
        {offer.options.map((o) => (
          <button key={o.id} className={`offer-card ${opt === o.id ? "on" : ""}`} onClick={() => setOpt(o.id)}>
            <div className="row between"><b>{o.label}</b>{opt === o.id && <span className="badge red">{t("выбрано")}</span>}</div>
            <div className="big mt">{money(o.amount)}</div>
            <dl className="kv mt">
              <dt>{t("Срок")}</dt><dd>{months(o.term_months)}</dd>
              <dt>{t("Ставка")}</dt><dd>{o.rate}{t("% годовых")}</dd>
              <dt>{o.revolving ? t("Проценты в месяц (макс.)") : t("Платёж в месяц")}</dt><dd><b>{money(o.monthly_payment)}</b></dd>
              <dt>{t("Переплата")}</dt><dd>{money(o.total_interest)}</dd>
            </dl>
          </button>
        ))}
      </div>
      {offer.conditions.length > 0 && <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>{offer.conditions.map((c) => <li key={c}>{c}</li>)}</ul>}
      <ErrorBox error={error} />
      <div className="row">
        <button className="btn primary" onClick={() => act("accept", { option_id: opt })}>{t("Принять и перейти к подписанию")}</button>
        <button className="btn ghost" onClick={() => confirm(t("Отказаться от предложения? Заявка будет закрыта.")) && act("cancel", { comment: t("Клиент отказался от предложения") })}>
          
          {t("Отказаться")}
        </button>
      </div>
    </div>
  );
}

function SigningBlock({ app, onChange }: { app: Application; onChange: (a: Application) => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<any>(null);
  const option = app.signing?.option;
  return (
    <div className="card stack lg">
      <h2>{t("Подписание договора")}</h2>
      <dl className="kv">
        <dt>{t("Сумма")}</dt><dd>{money(option?.amount)}</dd>
        <dt>{t("Срок и ставка")}</dt><dd>{months(option?.term_months)}, {option?.rate}%</dd>
        <dt>{t("Платёж")}</dt><dd>{money(option?.monthly_payment)}  {t("/ мес")}</dd>
      </dl>
      <div className="stack" style={{ gap: 6 }}>
        {(app.signing?.documents ?? []).map((d: string) => <div key={d} className="row small">📄 {d} <span className="muted">{t("— сформирован")}</span></div>)}
      </div>
      <div className="code-box">
        <span style={{ fontSize: 28 }}>🔐</span>
        <div>
          <div className="small" style={{ opacity: 0.8 }}>{t("Код подтверждения простой электронной подписи (в демо показан прямо в кабинете вместо push-уведомления)")}</div>
          <div className="code">{app.signing?.demo_code}</div>
        </div>
      </div>
      <div className="row">
        <input className="input" style={{ width: 200, fontSize: 20, letterSpacing: "0.2em" }} maxLength={6} inputMode="numeric"
          placeholder="••••••" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
        <button className="btn primary" disabled={code.length !== 6} onClick={async () => {
          setError(null);
          try { onChange(await api<Application>(`/api/applications/${app.id}/sign`, { body: { version: app.version, code } })); }
          catch (e) { setError(e); }
        }}>{t("Подписать договор")}</button>
      </div>
      <ErrorBox error={error} />
    </div>
  );
}

function LoanBlock({ app }: { app: Application }) {
  const loan = app.loan;
  return (
    <div className="card stack lg">
      <div className="row between">
        <h2>{t("🎉 Кредит выдан")}</h2>
        <span className="badge ok">{t("Договор")} {loan.contract_number}</span>
      </div>
      <div className="grid g4">
        <div className="stat accent"><div className="label">{t("Сумма")}</div><div className="value">{money(loan.amount)}</div></div>
        <div className="stat"><div className="label">{t("Ставка")}</div><div className="value">{loan.rate}%</div></div>
        <div className="stat"><div className="label">{t("Срок")}</div><div className="value">{loan.term_months}  {t("мес.")}</div></div>
        <div className="stat"><div className="label">{loan.revolving ? t("Лимит овердрафта") : t("Платёж")}</div><div className="value">{money(loan.revolving ? loan.amount : loan.monthly_payment)}</div></div>
      </div>
      <p className="muted">{t("Деньги зачислены на расчётный счёт")} {loan.account} · {dateTime(loan.disbursed_at)}</p>
      {loan.schedule?.length > 0 && (
        <details>
          <summary>{t("График платежей (")}{loan.schedule.length})</summary>
          <table className="tbl mt">
            <thead><tr><th>№</th><th>{t("Дата")}</th><th>{t("Платёж")}</th><th>{t("Основной долг")}</th><th>{t("Проценты")}</th><th>{t("Остаток")}</th></tr></thead>
            <tbody>
              {loan.schedule.map((r: any) => (
                <tr key={r.n}><td>{r.n}</td><td>{date(r.date)}</td><td>{money(r.payment)}</td><td>{money(r.principal)}</td><td>{money(r.interest)}</td><td>{money(r.balance)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

export default function ApplicationPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [app, setApp] = useState<Application | null>(null);
  const [error, setError] = useState<any>(null);

  const load = useCallback(() => api<Application>(`/api/applications/${id}`).then(setApp).catch(setError), [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!app || !POLL_STATUSES.includes(app.status)) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [app?.status, load]);

  if (error) return <ErrorBox error={error} />;
  if (!app) return <Loader />;

  const missing = app.requested_documents.filter((d) => !app.documents.some((x) => x.doc_type === d.code && x.status !== "REJECTED"));
  const act = async (path: string, body: object = {}) => {
    setError(null);
    try { setApp(await api<Application>(`/api/applications/${app.id}/${path}`, { body: { version: app.version, ...body } })); }
    catch (e) { setError(e); }
  };
  const pose = ["APPROVED", "COUNTER_OFFER", "DISBURSED"].includes(app.status) ? "wave" : app.status === "INFO_REQUESTED" ? "notes" : "sit";

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <div className="row"><h1>{t("Заявка")} {app.number}</h1><StatusBadge status={app.status} label={app.status_label} /></div>
          <p>{app.product_name ?? t("Продукт не выбран")} · {money(app.amount)} · {months(app.term_months)} · {app.company.name}</p>
        </div>
        <Link to="/applications" className="btn ghost sm">{t("← Все заявки")}</Link>
      </div>

      {app.status === "DRAFT" ? (
        <DraftForm initial={app} onSubmitted={(a) => { setApp(a); window.scrollTo({ top: 0 }); }} />
      ) : (
        <>
          <div className="card">
            <Track steps={app.track.steps} current={app.track.current} failed={app.status === "REJECTED" || app.status === "CANCELLED"} />
          </div>

          <AlfikSay pose={pose as any}>
            {app.alfik.say}
            {app.alfik.eta && <div className="small muted mt">{t("⏱ Обычно занимает")} {app.alfik.eta}</div>}
            {app.alfik.todo && <div className="small mt"><b>{t("Что сделать:")}</b> {app.alfik.todo}</div>}
          </AlfikSay>

          <ErrorBox error={error} />

          {[...PROCESSING.filter((s) => s !== "ISSUING"), "MANUAL_REVIEW"].includes(app.status) && (
            <div className="card"><h3 style={{ marginBottom: 14 }}>{t("Что происходит с заявкой")}</h3><Processing app={app} /></div>
          )}

          {app.status === "INFO_REQUESTED" && (
            <div className="card stack">
              <h2>{t("Нужны документы")}</h2>
              {app.timeline.filter((e) => e.to_status === "INFO_REQUESTED").slice(-1).map((e) => <p key={e.id} className="muted">{e.message}</p>)}
              {app.requested_documents.map((d) => <DocUpload key={d.code} app={app} code={d.code} label={d.label} required onUploaded={setApp} />)}
              {app.statement && <StatementCard s={app.statement} declared={app.form_data.monthly_revenue} />}
              {app.requested_documents.some((d) => d.code === "bank_statement") && <SampleStatements />}
              <div className="row mt">
                <button className="btn primary" disabled={missing.length > 0} onClick={() => act("resubmit")}>{t("Отправить повторно")}</button>
                {missing.length > 0 && <span className="small muted">{t("Осталось загрузить:")} {missing.length}</span>}
              </div>
            </div>
          )}

          {(app.status === "APPROVED" || app.status === "COUNTER_OFFER") && app.offer && <OfferBlock app={app} onChange={setApp} />}
          {app.status === "SIGNING" && <SigningBlock app={app} onChange={setApp} />}
          {app.status === "ISSUING" && <div className="card"><div className="substeps"><div className="substep run"><span className="st" />{t("Перечисляем деньги на расчётный счёт…")}</div></div></div>}
          {app.status === "DISBURSED" && app.loan && <LoanBlock app={app} />}

          {app.status === "REJECTED" && (
            <div className="card stack">
              <h2>{t("Почему так получилось")}</h2>
              {(app.decision?.reasons ?? []).map((r: any) => (
                <div key={r.code + r.text}>
                  <div className="alert bad">{r.text}</div>
                  {r.tips?.length > 0 && (
                    <AlfikSay pose="notes" size="sm" soft>
                      
                      {t("Что можно сделать:")}
                      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{r.tips.map((t: string) => <li key={t}>{t}</li>)}</ul>
                    </AlfikSay>
                  )}
                </div>
              ))}
              <div className="row mt">
                <button className="btn primary" onClick={() => nav("/precheck")}>{t("Проверить шансы заново")}</button>
                <button className="btn ghost" onClick={() => nav("/advisor")}>{t("Подобрать другой продукт")}</button>
              </div>
            </div>
          )}

          {app.status === "MANUAL_REVIEW" && (
            <div className="card stack">
              <h3>{t("Хотите ускорить рассмотрение?")}</h3>
              <p className="muted">{t("Можно приложить документы, которые помогут специалисту: выписку по счёту или отчётность.")}</p>
              <DocUpload app={app} code="bank_statement" label={t("Выписка по расчётному счёту за 6 месяцев")} onUploaded={setApp} />
              <DocUpload app={app} code="financial_statements" label={t("Бухгалтерская отчётность за последний год")} onUploaded={setApp} />
              {app.statement && <StatementCard s={app.statement} declared={app.form_data.monthly_revenue} />}
            </div>
          )}

          <div className="grid g2">
            <div className="card">
              <h3 style={{ marginBottom: 14 }}>{t("История заявки")}</h3>
              <div className="timeline">
                {[...app.timeline].reverse().map((e) => (
                  <div key={e.id} className="tl-item">
                    <div className={`tl-dot ${e.actor_type}`} />
                    <div>
                      <div className="what">{e.to_label ? <b>{e.to_label}. </b> : null}{e.message}</div>
                      <div className="when">{dateTime(e.created_at)} · {({ client: t("вы"), system: t("система"), underwriter: t("специалист банка") } as any)[e.actor_type]}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="card stack">
              <h3>{t("Параметры заявки")}</h3>
              <dl className="kv">
                <dt>{t("Продукт")}</dt><dd>{app.product_name}</dd>
                <dt>{t("Цель")}</dt><dd>{app.purpose_label}</dd>
                <dt>{t("Сумма")}</dt><dd>{money(app.amount)}</dd>
                <dt>{t("Срок")}</dt><dd>{months(app.term_months)}</dd>
                <dt>{t("Отправлена")}</dt><dd>{dateTime(app.submitted_at)}</dd>
                <dt>{t("Документы")}</dt><dd>{app.documents.length ? app.documents.map((d) => d.label).join(", ") : "—"}</dd>
              </dl>
              {app.allowed_transitions.includes("CANCELLED") && !["APPROVED", "COUNTER_OFFER"].includes(app.status) && (
                <button className="btn ghost sm" style={{ alignSelf: "flex-start" }}
                  onClick={() => confirm(t("Отменить заявку?")) && act("cancel")}>{t("Отменить заявку")}</button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
