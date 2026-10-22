import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ALFIK, ErrorBox, Gauge, useCatalog } from "../components/ui";
import { money, months } from "../format";
import type { Application } from "../types";
import { SPEECH_LANG, t } from "../i18n";

interface FieldItem { field: string; label: string; value: any; display: string; source: string; via: string }
interface StepResult {
  state: any;
  fields: FieldItem[];
  new_fields: string[];
  missing: { field: string; label: string }[];
  reply: string;
  ready: boolean;
  recommendation: any;
  llm_used: boolean;
}
interface Msg { role: "user" | "assistant"; text: string }

const CARD_FIELDS = [
  "amount", "purpose", "term_months", "monthly_revenue", "monthly_expenses", "existing_payments",
  "has_collateral", "comfortable_payment", "business_age_months", "urgency",
];
const LABELS: Record<string, string> = {
  amount: t("Сумма кредита"), purpose: t("Цель"), term_months: t("Срок"), monthly_revenue: t("Выручка в месяц"),
  monthly_expenses: t("Расходы в месяц"), existing_payments: t("Текущие кредиты"), has_collateral: t("Залог"),
  comfortable_payment: t("Комфортный платёж"), business_age_months: t("Возраст бизнеса"), urgency: t("Срочность"),
};
const REQUIRED = ["amount", "purpose", "term_months", "monthly_revenue", "monthly_expenses"];

// Web Speech API — встроенное распознавание речи браузера (Edge/Chrome), без отдельных сервисов в решении
const SpeechRecognition: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export default function Talk() {
  const catalog = useCatalog();
  const nav = useNavigate();
  const loc = useLocation();
  const [msgs, setMsgs] = useState<Msg[]>([{
    role: "assistant",
    text: t("Расскажите своими словами, на что нужны деньги, сколько и когда сможете вернуть. Можно голосом — нажмите на микрофон. А я сам заполню заявку 📝"),
  }]);
  const [res, setRes] = useState<StepResult | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [examples, setExamples] = useState<string[]>([]);
  const [product, setProduct] = useState<string | null>(null);
  const [error, setError] = useState<any>(null);
  const [flash, setFlash] = useState<string[]>([]);
  const rec = useRef<any>(null);
  const body = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  useEffect(() => { api("/api/intake/examples").then((r) => setExamples(r.examples)).catch(() => {}); }, []);
  useEffect(() => {
    const prefill = (loc.state as any)?.prefill;
    if (prefill && !started.current) { started.current = true; send(prefill); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight, behavior: "smooth" }); }, [msgs, busy]);

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setText("");
    setError(null);
    setMsgs((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    try {
      const r = await api<StepResult>("/api/intake/message", { body: { message, state: res?.state ?? null } });
      setRes(r);
      setFlash(r.new_fields);
      setTimeout(() => setFlash([]), 1800);
      if (r.recommendation) setProduct(r.recommendation.product_code);
      setMsgs((m) => [...m, { role: "assistant", text: r.reply }]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  function toggleMic() {
    if (!SpeechRecognition) return;
    if (listening) { rec.current?.stop(); return; }
    const r = new SpeechRecognition();
    r.lang = SPEECH_LANG;  // распознавание речи на языке интерфейса: ru-RU / en-US / zh-CN
    r.interimResults = true;
    r.continuous = false;
    let finalText = "";
    r.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      setText((finalText + " " + interim).trim());
    };
    r.onerror = () => setListening(false);
    r.onend = () => {
      setListening(false);
      if (finalText.trim()) send(finalText.trim());
    };
    rec.current = r;
    setListening(true);
    r.start();
  }

  async function create() {
    setError(null);
    try {
      const app = await api<Application>("/api/intake/create", { body: { state: res!.state, product_code: product } });
      nav(`/applications/${app.id}`);
    } catch (e) { setError(e); }
  }

  const byField = Object.fromEntries((res?.fields ?? []).map((f) => [f.field, f]));
  const filled = REQUIRED.filter((f) => byField[f]).length;
  const r = res?.recommendation;
  const pose = res?.ready ? "wave" : busy ? "notes" : "sit";

  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Расскажите Альфику")}</h1>
          <p>{t("Опишите задачу своими словами — Альфик поймёт и сам заполнит заявку")}</p>
        </div>
        {res && <button className="btn ghost" onClick={() => { setRes(null); setMsgs(msgs.slice(0, 1)); setProduct(null); }}>{t("Начать заново")}</button>}
      </div>

      <div className="talk-grid">
        <div className="card talk-chat">
          <div className="talk-hero">
            <img src={ALFIK[pose as keyof typeof ALFIK]} alt={t("Альфик")} className={`bob ${listening ? "listening" : ""}`} />
            {listening && <div className="talk-wave"><span /><span /><span /><span /><span /></div>}
          </div>
          <div className="talk-msgs" ref={body}>
            {msgs.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
            {busy && <div className="msg assistant typing"><span /><span /><span /></div>}
          </div>
          {msgs.length === 1 && examples.length > 0 && (
            <div className="stack" style={{ gap: 6 }}>
              <span className="small muted">{t("Например:")}</span>
              {examples.map((e) => <button key={e} className="example" onClick={() => send(e)}>«{e}»</button>)}
            </div>
          )}
          <form className="talk-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
            {SpeechRecognition ? (
              <button type="button" className={`mic ${listening ? "on" : ""}`} onClick={toggleMic}
                aria-label={listening ? t("Остановить запись") : t("Говорить")} title={t("Сказать голосом")}>🎙</button>
            ) : null}
            <input className="input" value={text} onChange={(e) => setText(e.target.value)} maxLength={3000}
              placeholder={listening ? t("Слушаю…") : t("Например: нужно 2 млн на оборудование, верну за 3 года…")} />
            <button className="btn primary" disabled={busy || !text.trim()}>➤</button>
          </form>
          <ErrorBox error={error} />
        </div>

        <div className="stack">
          <div className="card stack">
            <div className="row between">
              <h3>{t("Заявка заполняется")}</h3>
              <span className="badge neutral">{filled}  {t("из")} {REQUIRED.length}</span>
            </div>
            <div className="fit-bar"><div style={{ width: `${(filled / REQUIRED.length) * 100}%` }} /></div>
            <div className="talk-fields">
              {CARD_FIELDS.map((f) => {
                const item = byField[f];
                if (!item && !REQUIRED.includes(f)) return null;
                return (
                  <div key={f} className={`talk-field ${item ? "ok" : ""} ${flash.includes(f) ? "flash" : ""} ${res?.missing[0]?.field === f ? "asking" : ""}`}>
                    <span className="tf-ico">{item ? "✓" : "○"}</span>
                    <div style={{ minWidth: 0 }}>
                      <div className="small muted">{LABELS[f]}</div>
                      <b>{item ? item.display : "—"}</b>
                      {item?.source && (
                        <div className="tf-src">
                          {item.via === "egrul" ? "🏛 " : item.via === "llm" ? "✨ " : "💬 "}
                          {item.via === "egrul" || item.via === "llm" ? item.source : `«${item.source}»`}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {res?.llm_used && <span className="small muted">{t("✨ Часть данных понята локальной ИИ-моделью")}</span>}
          </div>

          {r && (
            <div className={`card stack ${res?.ready ? "talk-ready" : ""}`}>
              <div className="row between" style={{ alignItems: "flex-start" }}>
                <div>
                  <span className="small muted">{t("Альфик подобрал")}</span>
                  <h3>{catalog?.products.find((p) => p.code === product)?.name ?? r.product_name}</h3>
                </div>
                {r.readiness && <div className="gauge-sm"><Gauge value={r.readiness.readiness} label={t("готовность")} /></div>}
              </div>
              <dl className="kv">
                <dt>{t("Сумма и срок")}</dt><dd>{money(r.amount)}  {t("на")} {months(r.term_months)}</dd>
                <dt>{t("Платёж")}</dt><dd><b>{money(r.estimate.monthly_payment)}</b>  {t("/ мес (ставка от")} {r.estimate.rate}%)</dd>
                <dt>{t("Переплата")}</dt><dd>{money(r.estimate.total_interest)}</dd>
              </dl>
              {r.comfort_hint && <div className="alert info small">💡 {r.comfort_hint}</div>}
              {r.readiness?.suggestion && <div className="alert info small">💡 {r.readiness.suggestion.text}</div>}
              {r.readiness?.blockers?.length > 0 && <div className="alert warn small">{r.readiness.blockers.join(". ")}</div>}
              {catalog && r.alternatives?.length > 0 && (
                <div className="chips">
                  {[r.product_code, ...r.alternatives].map((code: string) => (
                    <button key={code} className={`chip ${product === code ? "on" : ""}`} onClick={() => setProduct(code)}>
                      {catalog.products.find((p) => p.code === code)?.name}
                    </button>
                  ))}
                </div>
              )}
              <button className="btn primary" disabled={!res?.ready} onClick={create}>
                {res?.ready ? t("Создать черновик заявки") : t("Осталось уточнить: {0}", res?.missing.map((m) => m.label.toLowerCase()).join(", "))}
              </button>
              <span className="small muted">{t("Предварительный расчёт; решение принимает банк после проверки данных.")}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
