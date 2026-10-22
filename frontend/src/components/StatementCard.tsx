import { money } from "../format";
import { AlfikSay } from "./ui";
import { t } from "../i18n";

const MONTHS = [t("янв"), t("фев"), t("мар"), t("апр"), t("май"), t("июн"), t("июл"), t("авг"), t("сен"), t("окт"), t("ноя"), t("дек")];

export interface StatementData {
  format: string;
  period_from: string;
  period_to: string;
  transactions: number;
  months: { month: string; inflow: number; outflow: number; excluded: number; full: boolean }[];
  months_used: number;
  avg_monthly_inflow: number;
  avg_monthly_outflow: number;
  excluded_total: number;
  top_counterparties: { name: string; amount: number; share: number }[];
  top_share: number;
  deviation_from_declared: number | null;
  declared_monthly_revenue: number | null;
  flags: string[];
  filename?: string;
}

export function StatementChart({ s }: { s: StatementData }) {
  const max = Math.max(...s.months.map((m) => Math.max(m.inflow, m.outflow)), 1);
  return (
    <div className="st-chart" role="img" aria-label={t("Поступления и списания по месяцам")}>
      {s.months.map((m) => {
        const [y, mm] = m.month.split("-");
        return (
          <div key={m.month} className={`st-col ${m.full ? "" : "partial"}`}
            title={t("{0} {1}: поступления {2}, списания {3}{4}", MONTHS[Number(mm) - 1], y, money(m.inflow), money(m.outflow), m.full ? "" : t(" (неполный месяц)"))}>
            <div className="st-bars">
              <div className="st-in" style={{ height: `${(m.inflow / max) * 100}%` }} />
              <div className="st-out" style={{ height: `${(m.outflow / max) * 100}%` }} />
            </div>
            <span>{MONTHS[Number(mm) - 1]}</span>
          </div>
        );
      })}
      <div className="st-avg" style={{ bottom: `${22 + (s.avg_monthly_inflow / max) * 130}px` }}>
        <span>{t("среднее")} {money(s.avg_monthly_inflow)}</span>
      </div>
    </div>
  );
}

export default function StatementCard({ s, onApplyRevenue, bank, declared: declaredNow }: {
  s: StatementData; onApplyRevenue?: (v: number) => void; bank?: boolean; declared?: number | null;
}) {
  // Сверяем с текущей цифрой анкеты: клиент мог изменить её после загрузки выписки
  const declared = declaredNow ?? s.declared_monthly_revenue;
  const dev = declared ? (s.avg_monthly_inflow - declared) / declared : null;
  const confirms = dev != null && dev >= -0.25;
  return (
    <div className="card flat stack">
      <div className="row between">
        <h3>📊 {bank ? t("Разбор выписки") : t("Альфик прочитал выписку")}</h3>
        <span className="badge neutral">{s.format === "1c" ? t("1С «Клиент-Банк»") : "CSV"} · {s.transactions}  {t("операций")}</span>
      </div>
      <StatementChart s={s} />
      <div className="row small muted" style={{ gap: 14 }}>
        <span><i className="legend-dot in" />  {t("поступления")}</span><span><i className="legend-dot out" />  {t("списания")}</span>
        <span>{t("светлые столбцы — неполные месяцы, в среднее не входят")}</span>
      </div>
      <div className="grid g3">
        <div className="stat"><div className="label">{t("Очищенные поступления / мес")}</div><div className="value">{money(s.avg_monthly_inflow)}</div></div>
        <div className="stat"><div className="label">{t("Списания / мес")}</div><div className="value">{money(s.avg_monthly_outflow)}</div></div>
        <div className="stat">
          <div className="label">{t("В анкете")}</div>
          <div className="value">{money(declared)}</div>
          {dev != null && <div className={`small ${confirms ? "pos" : "neg"}`}>{confirms ? t("✓ подтверждено") : t("⚠ выписка ниже")} ({dev > 0 ? "+" : ""}{Math.round(dev * 100)}%)</div>}
        </div>
      </div>
      {s.excluded_total > 0 && (
        <p className="small muted">{t("Не считаю выручкой")} {money(s.excluded_total)}{t(": переводы со своих счетов и полученные займы.")}</p>
      )}
      {bank && s.top_counterparties.length > 0 && (
        <table className="tbl">
          <thead><tr><th>{t("Крупнейшие плательщики")}</th><th>{t("Сумма")}</th><th>{t("Доля")}</th></tr></thead>
          <tbody>{s.top_counterparties.map((c) => <tr key={c.name}><td>{c.name}</td><td>{money(c.amount)}</td><td>{Math.round(c.share * 100)}%</td></tr>)}</tbody>
        </table>
      )}
      {s.flags.map((f) => <div key={f} className="alert warn small">⚠ {f}</div>)}
      {!bank && (
        <AlfikSay size="sm" pose="notes" soft>
          {confirms
            ? t("Обороты по выписке подтверждают вашу выручку — это плюс к оценке: банку не придётся сомневаться в цифрах.")
            : dev != null
              ? t("По выписке поступления в среднем {0} в месяц. Банк будет считать лимит по выписке, поэтому лучше сразу указать реальную цифру.", money(s.avg_monthly_inflow))
              : t("Средние поступления — {0} в месяц. Я подставлю их в анкету, если вы её ещё не заполнили.", money(s.avg_monthly_inflow))}
          {onApplyRevenue && !confirms && (
            <div className="mt"><button className="btn dark sm" onClick={() => onApplyRevenue(s.avg_monthly_inflow)}>{t("Подставить выручку из выписки")}</button></div>
          )}
        </AlfikSay>
      )}
    </div>
  );
}

const SAMPLES = [
  { file: "vypiska_kolosok_1c.txt", label: t("ООО «Колосок» — 1С") },
  { file: "vypiska_kolosok.csv", label: t("ООО «Колосок» — CSV") },
  { file: "vypiska_stroy_1c.txt", label: t("ООО «СтройМонтаж Плюс» — 1С") },
  { file: "vypiska_flora_1c.txt", label: t("ИП Смирнова — 1С") },
];

export function SampleStatements() {
  return (
    <details className="small">
      <summary>{t("Нет выписки под рукой? Скачайте синтетический пример")}</summary>
      <div className="chips mt">
        {SAMPLES.map((s) => <a key={s.file} className="chip" href={`/samples/${s.file}`} download>{s.label}</a>)}
      </div>
      <p className="muted mt">{t("Выгрузку в формате 1С «Клиент-Банк» можно получить в любом интернет-банке: «Выписка → Экспорт в 1С».")}</p>
    </details>
  );
}
