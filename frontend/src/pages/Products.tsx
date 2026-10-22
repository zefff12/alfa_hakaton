import { useNavigate } from "react-router-dom";
import { BadgePercent, Calendar, Clock, Info, Shield, Wallet } from "lucide-react";
import { Loader, useCatalog } from "../components/ui";
import { money, months } from "../format";
import { t } from "../i18n";
import { productArt, productIcon } from "../types";

const COLLATERAL = { none: t("Без залога"), optional: t("Залог по желанию"), required: t("С залогом") };

export default function Products() {
  const nav = useNavigate();
  const catalog = useCatalog();
  if (!catalog) return <Loader />;
  return (
    <div className="stack lg">
      <div className="page-head">
        <div>
          <h1>{t("Продукты для бизнеса")}</h1>
          <p>{t("Все кредитные продукты банка. Не знаете, что выбрать, — запустите подбор.")}</p>
        </div>
        <button className="btn primary" onClick={() => nav("/match")}>{t("Подобрать кредит")}</button>
      </div>
      <div className="grid g3">
        {catalog.products.map((p) => (
          <div key={p.code} className="fav-card">
            <div className="row nowrap">
              <div className="sc-icon" style={{ width: 52, height: 52 }}><img src={productIcon(p.code)} alt="" style={{ width: 44, height: 44 }} /></div>
              <div><h3 style={{ paddingRight: 0 }}>{p.name}</h3><div className="sub">{p.short}</div></div>
            </div>
            <div className="art"><img src={productArt(p.code)} alt="" /></div>
            <p className="text-2 small">{p.description}</p>
            <div className="fav-row"><Wallet size={20} /><div><div className="l">{t("Сумма")}</div><div className="v">{money(p.min_amount)} — {money(p.max_amount)}</div></div></div>
            <div className="fav-row"><Calendar size={20} /><div><div className="l">{t("Срок")}</div><div className="v">{t("до {0}", months(p.max_term))}</div></div></div>
            <div className="fav-row"><BadgePercent size={20} /><div><div className="l">{t("Ставка")}</div><div className="v cyan">{t("от {0}%", p.base_rate)}</div></div></div>
            <div className="row small text-2" style={{ gap: 16 }}>
              <span className="row nowrap" style={{ gap: 6 }}><Clock size={16} />{p.decision_time}</span>
              <span className="row nowrap" style={{ gap: 6 }}><Shield size={16} />{COLLATERAL[p.collateral]}</span>
            </div>
            <div className="spacer" />
            <div className="two">
              <button className="btn primary sm" onClick={() => nav(`/offers/${p.code}`)}><Info size={16} />{t("Подробнее")}</button>
              <button className="btn ghost sm" onClick={() => nav(`/advisor?calc=1&product=${p.code}`)}>{t("Калькулятор")}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
