import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { StatusBadge } from "../../components/ui";
import { dateTime, money } from "../../format";

const TABS = [
  { key: "manual", label: "Ручное рассмотрение" },
  { key: "processing", label: "В конвейере" },
  { key: "waiting_client", label: "Ждут клиента" },
  { key: "done", label: "Завершены" },
  { key: "", label: "Все" },
];

export default function BankQueue() {
  const [tab, setTab] = useState("manual");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [m, setM] = useState<any>(null);
  const nav = useNavigate();

  useEffect(() => {
    const load = () => {
      api<any[]>(`/api/bank/applications?queue=${tab}${q ? `&q=${encodeURIComponent(q)}` : ""}`).then(setRows);
      api("/api/bank/metrics").then(setM);
    };
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [tab, q]);

  return (
    <div className="stack lg">
      <div className="page-head">
        <div><h1>Кредитный конвейер</h1><p>Заявки малого и микробизнеса: автоматическая обработка и ручное рассмотрение</p></div>
      </div>
      {m && (
        <div className="grid g4">
          <div className="stat accent"><div className="label">На ручном рассмотрении</div><div className="value">{m.manual_queue}</div></div>
          <div className="stat"><div className="label">Всего заявок</div><div className="value">{m.total}</div></div>
          <div className="stat"><div className="label">Доля одобрений</div><div className="value">{m.approval_rate == null ? "—" : `${Math.round(m.approval_rate * 100)}%`}</div></div>
          <div className="stat"><div className="label">Решено автоматически</div><div className="value">{m.auto_decision_share == null ? "—" : `${Math.round(m.auto_decision_share * 100)}%`}</div></div>
          <div className="stat"><div className="label">Среднее время до решения</div><div className="value">{m.avg_decision_seconds == null ? "—" : m.avg_decision_seconds < 120 ? `${m.avg_decision_seconds} сек` : `${Math.round(m.avg_decision_seconds / 60)} мин`}</div></div>
          <div className="stat"><div className="label">Выдано</div><div className="value">{money(m.disbursed_amount)}</div></div>
          <div className="card flat" style={{ gridColumn: "span 2", padding: 14 }}>
            <div className="small muted" style={{ marginBottom: 8 }}>По статусам</div>
            <div className="chips">{m.by_status.map((s: any) => <span key={s.status} className="badge neutral">{s.label}: {s.count}</span>)}</div>
          </div>
        </div>
      )}
      <div className="row between">
        <div className="pill-tabs">
          {TABS.map((t) => <button key={t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>{t.label}</button>)}
        </div>
        <input className="input" style={{ width: 280 }} placeholder="Поиск: номер, ИНН, компания" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="card" style={{ padding: 8 }}>
        {rows.length === 0 ? <div className="empty">В этой очереди пусто</div> : (
          <table className="tbl">
            <thead><tr><th>Заявка</th><th>Клиент</th><th>Продукт</th><th>Сумма</th><th>Скоринг</th><th>Статус</th><th>Причина</th><th>Обновлена</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="click" onClick={() => nav(`/bank/applications/${r.id}`)}>
                  <td><b>{r.number}</b></td>
                  <td>{r.company}<div className="small muted">ИНН {r.inn}</div></td>
                  <td>{r.product_code}</td>
                  <td>{money(r.amount)}<div className="small muted">{r.term_months} мес.</div></td>
                  <td>{r.score ? <><b>{r.score}</b> <span className="badge neutral">{r.risk_class}</span></> : "—"}</td>
                  <td><StatusBadge status={r.status} label={r.status_label} /></td>
                  <td className="small">{r.manual_reasons.join("; ")}</td>
                  <td className="muted small">{dateTime(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
