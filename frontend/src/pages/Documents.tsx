import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Check, CircleHelp, FileText, FolderOpen, MessageCircle, ScanSearch, Upload, X } from "lucide-react";
import { api, getToken } from "../api";
import { openAlfik } from "../components/Chat";
import { CheckList, StepsTimeline, TaskList, type Checks } from "../components/Progress";
import { SampleStatements } from "../components/StatementCard";
import { ErrorBox, Loader, StatusBadge } from "../components/ui";
import { dateTime, money } from "../format";
import { t } from "../i18n";
import type { Application } from "../types";

const UPLOAD_STATUSES = ["DRAFT", "INFO_REQUESTED", "MANUAL_REVIEW"];
const FAQ = [
  t("Какие документы нужны?"),
  t("Как выгрузить выписку из 1С?"),
  t("Почему выручка в выписке отличается от анкеты?"),
  t("Сколько времени занимает проверка?"),
];

function DocRow({ app, code, label, required, checkStatus, onUploaded }: {
  app: Application; code: string; label: string; required?: boolean; checkStatus?: string; onUploaded: (a: Application) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const docs = app.documents.filter((d) => d.doc_type === code && d.status !== "REJECTED");
  const last = docs[docs.length - 1];
  const canUpload = UPLOAD_STATUSES.includes(app.status);
  const bad = checkStatus === "error";
  const warn = checkStatus === "warn";
  const isStatement = code === "bank_statement" && app.statement;

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("doc_type", code);
    form.append("file", file);
    try { onUploaded(await api<Application>(`/api/applications/${app.id}/documents`, { form })); }
    catch (e: any) { setError(e.message); }
    setBusy(false);
    if (ref.current) ref.current.value = "";
  }

  return (
    <div className="doc-row" id={`doc-${code}`}>
      <span className={`stc ${bad ? "err" : warn ? "warn" : last ? "ok" : "wait"}`}>
        {bad ? <X size={18} /> : warn ? "!" : last ? <Check size={18} /> : null}
      </span>
      <span className="fi"><FileText size={24} /></span>
      <div style={{ minWidth: 0 }}>
        <b>{label}</b> {required && !last && <span className="badge warn">{t("нужен")}</span>}
        {last ? (
          <div className={`sub ${bad ? "bad" : "ok"}`}>
            {isStatement && !bad ? t("Загружено: {0} поступлений в месяц", money(app.statement.avg_monthly_inflow)) : `${last.filename} · ${dateTime(last.created_at)}`}
            {bad && ` — ${t("есть ошибка, загрузите другой файл")}`}
          </div>
        ) : (
          <div className="sub">{required ? t("Загрузите документ") : t("По желанию — ускорит рассмотрение")}</div>
        )}
        {error && <div className="small neg">{error}</div>}
      </div>
      <input ref={ref} type="file" hidden accept=".pdf,.jpg,.jpeg,.png,.txt,.csv,.xlsx,.docx"
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      {canUpload ? (
        <button className="dropzone-btn" disabled={busy} onClick={() => ref.current?.click()}>
          <Upload size={18} />{busy ? t("Загружаю…") : last ? t("Заменить") : t("Загрузить")}
        </button>
      ) : last ? <a className="btn ghost sm" href={`/api/documents/${last.id}/download`} onClick={(e) => { e.preventDefault(); download(last.id, last.filename); }}>{t("Скачать")}</a> : <span />}
    </div>
  );
}

async function download(id: number, filename: string) {
  const token = getToken();
  const r = await fetch(`/api/documents/${id}/download`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export default function Documents() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [apps, setApps] = useState<Application[] | null>(null);
  const [app, setApp] = useState<Application | null>(null);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [error, setError] = useState<any>(null);
  const appId = params.get("app");

  useEffect(() => { api<Application[]>("/api/applications").then(setApps).catch(setError); }, []);
  const chosen = appId ?? String((apps?.find((a) => !a.is_final) ?? apps?.[0])?.id ?? "");

  useEffect(() => {
    if (!chosen) return;
    api<Application>(`/api/applications/${chosen}`).then(setApp).catch(setError);
  }, [chosen]);
  useEffect(() => {
    if (!app) return;
    api<Checks>(`/api/applications/${app.id}/checks`).then(setChecks).catch(() => {});
  }, [app]);
  useEffect(() => {
    const doc = params.get("doc");
    if (doc && app) setTimeout(() => document.getElementById(`doc-${doc}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 200);
  }, [app, params]);

  if (error) return <ErrorBox error={error} />;
  if (!apps) return <Loader />;
  if (apps.length === 0) {
    return (
      <div className="card glow empty">
        <FolderOpen size={48} className="cyan" />
        <h2 className="mt">{t("Документов пока нет")}</h2>
        <p className="mt">{t("Документы появятся, когда вы начнёте заявку.")}</p>
        <button className="btn primary mt" onClick={() => nav("/match")}>{t("Подобрать кредит")}</button>
      </div>
    );
  }
  if (!app) return <Loader />;

  const byCode = Object.fromEntries((checks?.items ?? []).map((c) => [c.code, c.status]));
  const statementStatus = ["statement_owner", "revenue_statement", "statement_period"].map((c) => byCode[c])
    .find((s) => s === "error") ?? ["statement_owner", "revenue_statement", "statement_period"].map((c) => byCode[c]).find((s) => s === "warn");
  const needed = [...app.required_documents, ...app.requested_documents.filter((d) => !app.required_documents.some((r) => r.code === d.code))];
  const rows = [
    ...needed.map((d) => ({ ...d, required: true })),
    ...(needed.some((d) => d.code === "bank_statement") ? [] : [{ code: "bank_statement", label: t("Выписка по расчётному счёту за 6 месяцев"), required: false }]),
    ...(needed.some((d) => d.code === "founding_docs") ? [] : [{ code: "founding_docs", label: t("Учредительные документы (устав, решение о назначении руководителя)"), required: false }]),
    { code: "other", label: t("Дополнительные документы"), required: false },
  ];
  const formOk = byCode.form === "ok";
  const total = rows.filter((r) => r.required).length + 1;
  const uploaded = rows.filter((r) => r.required && app.documents.some((d) => d.doc_type === r.code && d.status !== "REJECTED")).length + (formOk ? 1 : 0);
  const problems = checks ? checks.summary.counts.error + checks.summary.counts.warn : 0;
  const onUploaded = (a: Application) => setApp(a);

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Документы")}</h1>
          <p>{t("Загрузите документы — Альфик проверит их и найдёт несоответствия до рассмотрения заявки")}</p>
        </div>
        <label className="field" style={{ minWidth: 300 }}>
          <span>{t("Заявка")}</span>
          <select className="input" value={chosen} onChange={(e) => setParams({ app: e.target.value })}>
            {apps.map((a) => <option key={a.id} value={a.id}>{a.number} · {a.product_name ?? "—"} · {a.status_label}</option>)}
          </select>
        </label>
      </div>

      <div className="match-grid side-380">
        <div className="stack lg">
          <div className="card glow stack">
            <div className="row between">
              <h2>{t("Список документов")}</h2>
              <span className="text-2">{t("{0} из {1} загружено", uploaded, total)}</span>
            </div>
            <div className="progress"><div style={{ width: `${(uploaded / total) * 100}%` }} /></div>
            <div className="doc-row">
              <span className={`stc ${formOk ? "ok" : byCode.form === "error" ? "err" : "wait"}`}>{formOk ? <Check size={18} /> : byCode.form === "error" ? <X size={18} /> : null}</span>
              <span className="fi"><FileText size={24} /></span>
              <div>
                <b>{t("Анкета на кредит")}</b>
                <div className={`sub ${formOk ? "ok" : "bad"}`}>{formOk ? t("Заполнена") : checks?.items.find((c) => c.code === "form")?.message ?? ""}</div>
              </div>
              <button className="btn ghost sm" onClick={() => nav(`/applications/${app.id}`)}>{app.status === "DRAFT" ? t("Заполнить") : t("Открыть")}</button>
            </div>
            {rows.map((r) => (
              <DocRow key={r.code} app={app} code={r.code} label={r.label} required={r.required}
                checkStatus={r.code === "bank_statement" ? statementStatus : undefined} onUploaded={onUploaded} />
            ))}
            {!UPLOAD_STATUSES.includes(app.status) && (
              <div className="alert info">{t("На этапе «{0}» документы не принимаются — список показан для справки.", app.status_label)}</div>
            )}
            <SampleStatements />
          </div>

          <div className="card stack">
            <div className="row between">
              <div className="row nowrap"><ScanSearch size={26} className="cyan" /><h2>{t("Проверка Альфиком")}</h2></div>
              {checks && (problems
                ? <span className="badge warn">{t("Найдено несоответствий: {0}", problems)}</span>
                : <span className="badge ok">{t("Несоответствий нет")}</span>)}
            </div>
            <div className="alert info">
              {t("Альфик сверяет анкету с выпиской, данными ФНС, БКИ и ЕГРЮЛ и показывает источник каждого значения. Ошибку в анкете можно исправить одним нажатием.")}
            </div>
            {checks ? <CheckList app={app} checks={checks} onFixed={(a, c) => { setApp(a); setChecks(c); }} /> : <Loader />}
          </div>
        </div>

        <div className="stack lg">
          <div className="card stack">
            <div className="row between">
              <h3>{t("Этапы проверки")}</h3>
              <StatusBadge status={app.status} label={app.status_label} />
            </div>
            <StepsTimeline steps={app.steps.slice(0, 4)} />
            <TaskList app={app} tasks={app.tasks.filter((x) => x.type === "upload")} />
            <button className="btn ghost sm" onClick={() => nav(`/applications/${app.id}`)}>{t("Открыть заявку {0}", app.number)}</button>
          </div>
          <div className="card stack">
            <div className="row nowrap"><CircleHelp size={24} className="cyan" /><h3>{t("Нужна помощь?")}</h3></div>
            {FAQ.map((q) => (
              <button key={q} className="faq-item" onClick={() => openAlfik(q)}><span className="fq"><MessageCircle size={18} /></span>{q}</button>
            ))}
          </div>
          <div className="card stack">
            <h3>{t("История по заявке")}</h3>
            <div className="timeline">
              {[...app.timeline].reverse().slice(0, 6).map((e) => (
                <div key={e.id} className="tl-item">
                  <div className={`tl-dot ${e.actor_type}`} />
                  <div><div className="what">{e.message}</div><div className="when">{dateTime(e.created_at)}</div></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
