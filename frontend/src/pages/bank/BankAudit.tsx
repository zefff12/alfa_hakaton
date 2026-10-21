import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { dateTime } from "../../format";

export default function BankAudit() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api<any[]>("/api/bank/audit?limit=200").then(setRows); }, []);
  return (
    <div className="stack lg">
      <div className="page-head"><div><h1>Журнал событий</h1><p>Аудит всех переходов статусов и действий участников</p></div></div>
      <div className="card" style={{ padding: 8 }}>
        <table className="tbl">
          <thead><tr><th>Время</th><th>Заявка</th><th>Событие</th><th>Переход</th><th>Кто</th><th>Описание</th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td className="small muted">{dateTime(e.created_at)}</td>
                <td><Link to={`/bank/applications/${e.application_id}`}>{e.number}</Link></td>
                <td className="small">{e.event_type}</td>
                <td className="small">{e.from_status ?? "—"} → {e.to_status ?? "—"}</td>
                <td className="small">{e.actor_type}</td>
                <td className="small">{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
