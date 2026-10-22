import { useNavigate, useOutletContext } from "react-router-dom";
import { Bell, CheckCheck, ChevronRight } from "lucide-react";
import type { Notification } from "../components/Layout";
import { dateTime } from "../format";
import { t } from "../i18n";

interface Ctx { notifications: { items: Notification[]; unread: number; readAll: () => void } }

export default function Notifications() {
  const nav = useNavigate();
  const { notifications: n } = useOutletContext<Ctx>();
  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Уведомления")}</h1>
          <p>{t("Все события по заявкам: решения банка, запросы документов, выдача")}</p>
        </div>
        <button className="btn ghost" disabled={!n.unread} onClick={n.readAll}><CheckCheck size={18} />{t("Прочитать все")}</button>
      </div>
      {n.items.length === 0 ? (
        <div className="card glow empty"><Bell size={44} className="cyan" /><h3 className="mt">{t("Уведомлений пока нет")}</h3></div>
      ) : (
        <div className="card stack" style={{ padding: 10 }}>
          {n.items.map((x) => (
            <button key={x.id} className="faq-item" style={{ alignItems: "flex-start" }} disabled={!x.application_id}
              onClick={() => x.application_id && nav(`/applications/${x.application_id}`)}>
              <span className="fq" style={x.is_read ? undefined : { background: "var(--red)", boxShadow: "0 0 12px rgba(255,45,45,.5)" }}><Bell size={18} /></span>
              <div style={{ flex: 1 }}>
                <b>{x.title}</b>
                {x.body && <div className="small text-2">{x.body}</div>}
                <div className="small muted">{dateTime(x.created_at)}</div>
              </div>
              {x.application_id && <ChevronRight size={18} className="muted" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
