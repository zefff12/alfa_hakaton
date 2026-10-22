import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ALFIK, Loader, StatusBadge } from "../components/ui";
import { dateTime, money, months } from "../format";
import type { Application } from "../types";
import { t } from "../i18n";

export default function Applications() {
  const [apps, setApps] = useState<Application[] | null>(null);
  useEffect(() => { api<Application[]>("/api/applications").then(setApps); }, []);
  if (!apps) return <Loader />;

  return (
    <div className="stack lg">
      <div className="page-head">
        <div><h1>{t("Мои заявки")}</h1><p>{t("Все заявки компании и их статусы")}</p></div>
        <Link className="btn primary" to="/advisor">{t("+ Новая заявка")}</Link>
      </div>
      {apps.length === 0 ? (
        <div className="card empty">
          <img src={ALFIK.sit} alt="" className="bob" />
          <h3>{t("Заявок пока нет")}</h3>
          <p className="mt">{t("Давайте подберём кредит — я помогу на каждом шаге.")}</p>
          <Link className="btn primary mt" to="/advisor">{t("Подобрать кредит")}</Link>
        </div>
      ) : (
        <div className="card" style={{ padding: 8 }}>
          <table className="tbl">
            <thead><tr><th>{t("Номер")}</th><th>{t("Продукт")}</th><th>{t("Сумма")}</th><th>{t("Срок")}</th><th>{t("Статус")}</th><th>{t("Обновлена")}</th><th /></tr></thead>
            <tbody>
              {apps.map((a) => (
                <tr key={a.id}>
                  <td><b>{a.number}</b></td>
                  <td>{a.product_name ?? "—"}</td>
                  <td>{money(a.amount)}</td>
                  <td>{months(a.term_months)}</td>
                  <td><StatusBadge status={a.status} label={a.status_label} /></td>
                  <td className="muted">{dateTime(a.updated_at)}</td>
                  <td><Link className="btn ghost sm" to={`/applications/${a.id}`}>{a.status === "DRAFT" ? t("Продолжить") : t("Открыть")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
