import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, CircleAlert, CircleCheck, CircleX, Info, Lightbulb, Upload, Wand, X } from "lucide-react";
import { api } from "../api";
import { dateTime } from "../format";
import { t } from "../i18n";
import type { AppStep, AppTask, Application } from "../types";
import { ErrorBox } from "./ui";

/** Шкала заявки: что сделано ✓, что идёт сейчас ◌ и что впереди ○. */
export function StepsTimeline({ steps }: { steps: AppStep[] }) {
  return (
    <div className="vsteps">
      {steps.map((s, i) => (
        <div key={s.key} className={`vstep ${s.state}`}>
          <span className="num">
            {s.state === "done" ? <Check size={18} /> : s.state === "active" ? <span className="spinner" /> :
              s.state === "attention" ? "!" : s.state === "failed" ? <X size={16} /> : i + 1}
          </span>
          <div><b>{s.title}</b><div className="d">{s.detail}</div></div>
          <span className="at">{s.at ? dateTime(s.at) : ""}</span>
        </div>
      ))}
    </div>
  );
}

/** Конкретные задачи клиенту от банка — прямо в кабинете. */
export function TaskList({ app, tasks }: { app: Application; tasks: AppTask[] }) {
  const nav = useNavigate();
  if (!tasks.length) return null;
  return (
    <div className="stack">
      {tasks.map((task) => (
        <div key={task.title} className={`task ${task.done ? "done" : ""}`}>
          {task.done ? <CircleCheck size={22} className="pos" /> : <CircleAlert size={22} style={{ color: "var(--warn)" }} />}
          <div style={{ flex: 1 }}>
            <b>{task.title}</b>
            <div className="small muted">{task.done ? t("Готово — заявка продолжит путь автоматически") : t("Задача от банка")}</div>
          </div>
          {!task.done && task.type === "upload" && (
            <button className="btn primary sm" onClick={() => nav(`/documents?app=${app.id}&doc=${task.code}`)}><Upload size={16} />{t("Загрузить")}</button>
          )}
          {!task.done && task.type !== "upload" && (
            <button className="btn primary sm" onClick={() => document.getElementById("action")?.scrollIntoView({ behavior: "smooth" })}>{t("Перейти")}</button>
          )}
        </div>
      ))}
    </div>
  );
}

export interface CheckItem {
  code: string; title: string; status: "ok" | "warn" | "error" | "pending" | "info"; message: string;
  values: { label: string; value: string; origin: string }[];
  fix: { field: string; value: number; label: string } | null;
  hint: string | null;
}
export interface Checks { items: CheckItem[]; summary: { level: string; counts: Record<string, number>; fixable: number } }

const CHECK_ICON = {
  ok: <CircleCheck size={22} className="pos" />,
  warn: <CircleAlert size={22} style={{ color: "var(--warn)" }} />,
  error: <CircleX size={22} className="neg" />,
  pending: <span className="spinner" />,
  info: <Info size={22} style={{ color: "var(--info)" }} />,
};

/** Найденные Альфиком несоответствия: значения, их источники и исправление одним нажатием. */
export function CheckList({ app, checks, onFixed, onlyProblems }: {
  app: Application; checks: Checks; onFixed: (app: Application, checks: Checks) => void; onlyProblems?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<any>(null);
  const canFix = ["DRAFT", "INFO_REQUESTED"].includes(app.status);
  const items = onlyProblems ? checks.items.filter((c) => c.status === "warn" || c.status === "error") : checks.items;

  const fix = async (c: CheckItem) => {
    setBusy(c.code);
    setError(null);
    try {
      const r = await api<{ application: Application; checks: Checks }>(`/api/applications/${app.id}/fix`, { body: { field: c.fix!.field, value: c.fix!.value } });
      onFixed(r.application, r.checks);
    } catch (e) { setError(e); }
    setBusy(null);
  };

  return (
    <div className="stack">
      <ErrorBox error={error} />
      {items.map((c) => (
        <div key={c.code} className={`check-card ${c.status}`}>
          <div className="row nowrap" style={{ alignItems: "flex-start" }}>
            {CHECK_ICON[c.status]}
            <div style={{ flex: 1 }}>
              <b>{c.title}</b>
              <div className={`small ${c.status === "error" ? "neg" : c.status === "warn" ? "" : "muted"}`} style={c.status === "warn" ? { color: "var(--warn)" } : undefined}>{c.message}</div>
            </div>
          </div>
          {c.values.length > 0 && (
            <div className="check-vals">
              {c.values.map((v) => (
                <div key={v.label + v.origin} className="check-val">
                  <div className="src">{v.origin}</div>
                  <div className="small muted">{v.label}</div>
                  <b>{v.value}</b>
                </div>
              ))}
            </div>
          )}
          {c.hint && <div className="small muted"><Lightbulb size={14} style={{ verticalAlign: -2 }} /> {c.hint}</div>}
          {c.fix && (
            canFix
              ? <button className="btn cyan sm" style={{ alignSelf: "flex-start" }} disabled={busy === c.code} onClick={() => fix(c)}><Wand size={16} />{c.fix.label}</button>
              : <div className="small muted">{t("Исправить анкету можно до рассмотрения заявки — специалист учтёт расхождение.")}</div>
          )}
        </div>
      ))}
    </div>
  );
}
