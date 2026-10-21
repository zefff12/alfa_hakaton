import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ChatMsg } from "../types";
import { ALFIK } from "./ui";

const QUICK = ["Какой статус заявки?", "Какой кредит мне подойдёт?", "Каковы мои шансы?", "Платёж слишком высокий", "Какие нужны документы?", "Что такое овердрафт?"];

const TIPS: Record<string, string> = {
  "/": "Чем помочь?",
  "/advisor": "Помогу выбрать!",
  "/precheck": "Объясню каждый вопрос",
  "/feed": "Подобрал для вас",
};

export default function Chat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [llm, setLlm] = useState<{ available: boolean; model: string } | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const appMatch = loc.pathname.match(/^\/applications\/(\d+)/);

  useEffect(() => {
    if (!open) return;
    api<ChatMsg[]>("/api/assistant/history").then(setMsgs).catch(() => {});
    api("/api/assistant/status").then((s) => setLlm(s.llm)).catch(() => {});
  }, [open]);

  useEffect(() => {
    body.current?.scrollTo({ top: body.current.scrollHeight, behavior: "smooth" });
  }, [msgs, busy]);

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setText("");
    const tmp: ChatMsg = { id: -Date.now(), role: "user", content: message, source: null, meta: null, created_at: "" };
    setMsgs((m) => [...m, tmp]);
    setBusy(true);
    try {
      const reply = await api<ChatMsg>("/api/assistant/chat", {
        body: { message, application_id: appMatch ? Number(appMatch[1]) : null, page: loc.pathname },
      });
      setMsgs((m) => [...m, reply]);
    } catch (e: any) {
      setMsgs((m) => [...m, { ...tmp, id: -Date.now(), role: "assistant", content: e.message ?? "Не получилось ответить" }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="chat-fab" onClick={() => setOpen(true)} aria-label="Открыть чат с Альфиком">
        <span className="fab-tip">{TIPS[loc.pathname] ?? "Спросите меня!"}</span>
        <img src={ALFIK.wave} alt="" className="bob" />
      </button>
    );
  }

  return (
    <div className="chat-panel" role="dialog" aria-label="Чат с Альфиком">
      <div className="chat-head">
        <img src={ALFIK.wave} alt="" />
        <div>
          <b>Альфик</b>
          <small>{llm?.available ? `онлайн · ИИ ${llm.model}` : "онлайн · отвечаю по базе знаний"}</small>
        </div>
        <button onClick={() => setOpen(false)} aria-label="Закрыть">×</button>
      </div>
      <div className="chat-body" ref={body}>
        {msgs.length === 0 && (
          <div className="msg assistant">
            Привет! Я Альфик 👋 Помогу подобрать кредит, оценить шансы, заполнить заявку и объясню, что происходит на каждом этапе.
            Спросите что-нибудь или выберите вопрос ниже.
          </div>
        )}
        {msgs.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.content}
            {m.meta?.actions && m.meta.actions.length > 0 && (
              <div className="msg-actions">
                {m.meta.actions.map((a) => (
                  <button key={a.to + a.label} onClick={() => nav(a.to)}>{a.label}</button>
                ))}
              </div>
            )}
            {m.role === "assistant" && m.source === "llm" && <span className="src">ответ сгенерирован локальной ИИ-моделью</span>}
          </div>
        ))}
        {busy && <div className="msg assistant typing"><span /><span /><span /></div>}
      </div>
      <div className="chat-quick">
        {QUICK.map((q) => <button key={q} onClick={() => send(q)}>{q}</button>)}
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input className="input" placeholder="Напишите вопрос…" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
        <button className="btn primary" disabled={busy || !text.trim()}>➤</button>
      </form>
    </div>
  );
}
