import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { date, money, months } from "../format";
import type { Application } from "../types";
import Calculator from "./Calculator";
import DocUpload from "./DocUpload";
import StatementCard, { SampleStatements } from "./StatementCard";
import { AlfikSay, ErrorBox, Field, MoneyInput, useCatalog } from "./ui";
import { t } from "../i18n";

const STEPS = [t("Параметры"), t("Компания"), t("Финансы"), t("Документы"), t("Отправка")];
const OPTIONAL_DOCS = ["bank_statement", "financial_statements", "collateral_docs", "other"];

const HINTS = [
  t("Выберите продукт и параметры. Если платёж кажется высоким — нажмите «Платёж слишком высокий», я подберу условия."),
  t("Реквизиты я уже подтянул из ЕГРЮЛ — проверять и вводить их не нужно. Если что-то изменилось, банк обновит данные сам."),
  t("Укажите средние цифры за последние 6 месяцев. Не страшно, если неточно: банк сверит их с данными ФНС."),
  t("Для большинства заявок документы не нужны. Обязательные отмечены — остальное по желанию: выписка ускорит решение по крупным суммам."),
  t("Проверьте данные и дайте согласия. Запрос в БКИ — только с вашего согласия, это стандартная процедура."),
];

export default function DraftForm({ initial, onSubmitted }: { initial: Application; onSubmitted: (a: Application) => void }) {
  const catalog = useCatalog();
  const { user } = useAuth();
  const [app, setApp] = useState(initial);
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [egrul, setEgrul] = useState<any>(null);
  const [errors, setErrors] = useState<any>(null);
  const version = useRef(initial.version);
  const pending = useRef<Record<string, any>>({});
  const timer = useRef<number | undefined>(undefined);
  const chain = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    api(`/api/company/lookup/${initial.company.inn}`).then((r) => setEgrul(r.data)).catch(() => setEgrul(false));
  }, [initial.company.inn]);

  function flush() {
    const patch = pending.current;
    pending.current = {};
    if (!Object.keys(patch).length) return chain.current;
    setSaving("saving");
    chain.current = chain.current.then(async () => {
      try {
        const r = await api<Application>(`/api/applications/${app.id}`, { method: "PATCH", body: { ...patch, version: version.current } });
        version.current = r.version;
        setApp((cur) => ({ ...r, form_data: { ...r.form_data, ...cur.form_data }, consents: { ...r.consents, ...cur.consents } }));
        setSaving("saved");
      } catch (e: any) {
        setSaving("error");
        if (e.status === 409) {
          const fresh = await api<Application>(`/api/applications/${app.id}`);
          version.current = fresh.version;
          setApp(fresh);
        }
      }
    });
    return chain.current;
  }

  function update(patch: Partial<Application>) {
    setApp((cur) => ({
      ...cur, ...patch,
      form_data: patch.form_data ? { ...cur.form_data, ...patch.form_data } : cur.form_data,
      consents: patch.consents ? { ...cur.consents, ...patch.consents } : cur.consents,
    }));
    for (const [k, v] of Object.entries(patch)) {
      pending.current[k] = k === "form_data" || k === "consents" ? { ...(pending.current[k] ?? {}), ...(v as object) } : v;
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 600);
  }

  async function submit() {
    window.clearTimeout(timer.current);
    await flush();
    setErrors(null);
    try {
      const r = await api<Application>(`/api/applications/${app.id}/submit`, { body: { version: version.current } });
      onSubmitted(r);
    } catch (e) { setErrors(e); }
  }

  if (!catalog) return null;
  const product = catalog.products.find((p) => p.code === app.product_code);
  const fd = app.form_data;
  const net = (fd.monthly_revenue ?? 0) - (fd.monthly_expenses ?? 0);
  const payment = app.estimate?.monthly_payment ?? 0;
  const burden = net > 0 ? ((fd.existing_payments ?? 0) + payment) / net : null;
  const requiredCodes = app.required_documents.map((d) => d.code);
  const docLabel = (c: string) => catalog.document_types.find((d) => d.code === c)?.label ?? c;

  return (
    <div className="stack lg">
      <div className="row between">
        <div className="wizard-steps" style={{ marginBottom: 0 }}>
          {STEPS.map((s, i) => (
            <button key={s} className={i === step ? "on" : i < step ? "done" : ""} onClick={() => { flush(); setStep(i); }}>{i + 1}. {s}</button>
          ))}
        </div>
        <span className="save-state">
          {saving === "saving" ? t("Сохраняю…") : saving === "saved" ? t("✓ Черновик сохранён") : saving === "error" ? t("Не удалось сохранить") : t("Черновик сохраняется автоматически")}
        </span>
      </div>

      <AlfikSay pose={step === 4 ? "wave" : "notes"} size="sm">{HINTS[step]}</AlfikSay>

      {step === 0 && (
        <div className="card stack lg">
          <h3>{t("Кредитный продукт")}</h3>
          <div className="grid g3">
            {catalog.products.map((p) => (
              <button key={p.code} className={`product-card ${app.product_code === p.code ? "on" : ""}`}
                onClick={() => update({
                  product_code: p.code,
                  amount: Math.min(Math.max(app.amount ?? p.min_amount, p.min_amount), p.max_amount),
                  term_months: Math.min(Math.max(app.term_months ?? p.min_term, p.min_term), p.max_term),
                  purpose: p.purposes.includes(app.purpose ?? "") ? app.purpose : p.purposes[0],
                })}>
                <b>{p.name}</b>
                <small>{t("от")} {p.base_rate}{t("% · до")} {money(p.max_amount)} · {p.decision_time}</small>
              </button>
            ))}
          </div>
          {product && (
            <>
              <div className="grid g2">
                <Field label={t("Цель кредита")}>
                  <select className="input" value={app.purpose ?? ""} onChange={(e) => update({ purpose: e.target.value })}>
                    {catalog.purposes.filter((p) => product.purposes.includes(p.code) || p.code === "other").map((p) => (
                      <option key={p.code} value={p.code}>{p.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label={t("Комментарий к цели (необязательно)")}>
                  <input className="input" value={app.purpose_comment ?? ""} placeholder={t("Например: закупка муки к сезону")}
                    onChange={(e) => update({ purpose_comment: e.target.value })} />
                </Field>
              </div>
              <Calculator product={product} amount={app.amount ?? product.min_amount} term={app.term_months ?? product.min_term}
                hasCollateral={app.has_collateral} onChange={(amount, term_months) => update({ amount, term_months })} />
              {product.collateral !== "none" && (
                <div className="stack">
                  <label className="check">
                    <input type="checkbox" checked={app.has_collateral} onChange={(e) => update({ has_collateral: e.target.checked })} />
                    {product.collateral === "required" ? t("Предоставлю залог (обязательно для этого продукта)") : t("Готов предоставить залог — ставка будет ниже")}
                  </label>
                  {app.has_collateral && (
                    <input className="input" placeholder={t("Что в залоге? Например: хлебопекарная печь, 2024 г.")} value={app.collateral_description ?? ""}
                      onChange={(e) => update({ collateral_description: e.target.value })} />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {step === 1 && (
        <div className="card stack lg">
          <div className="row between">
            <h3>{egrul?.name ?? app.company.name}</h3>
            <span className="badge ok">{t("✓ Данные из ЕГРЮЛ")}</span>
          </div>
          {egrul === null && <p className="muted">{t("Запрашиваю ЕГРЮЛ…")}</p>}
          {egrul === false && <div className="alert warn">{t("Реестр сейчас недоступен — банк проверит реквизиты автоматически после отправки.")}</div>}
          {egrul && (
            <dl className="kv">
              <dt>{t("ИНН")}</dt><dd>{egrul.inn}</dd>
              <dt>{t("ОГРН")}</dt><dd>{egrul.ogrn}</dd>
              <dt>{t("Дата регистрации")}</dt><dd>{date(egrul.registered_at)}</dd>
              <dt>{t("Основной ОКВЭД")}</dt><dd>{egrul.okved} — {egrul.okved_name}</dd>
              <dt>{t("Руководитель")}</dt><dd>{egrul.director}</dd>
              <dt>{t("Адрес")}</dt><dd>{egrul.address}</dd>
              <dt>{t("Статус")}</dt><dd>{egrul.status === "ACTIVE" ? t("Действующая") : <span className="neg">{t("Не действует / ликвидация")}</span>}</dd>
            </dl>
          )}
          <div className="sep" />
          <h3>{t("Контактное лицо по заявке")}</h3>
          <div className="grid g2">
            <Field label={t("ФИО")}><input className="input" value={fd.contact_name ?? user?.full_name ?? ""} onChange={(e) => update({ form_data: { contact_name: e.target.value } })} /></Field>
            <Field label={t("Должность / роль")}><input className="input" value={fd.contact_position ?? user?.position ?? ""} onChange={(e) => update({ form_data: { contact_position: e.target.value } })} /></Field>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card stack lg">
          <div className="grid g3">
            <Field label={t("Средняя выручка в месяц, ₽")} hint={t("поступления от клиентов")}>
              <MoneyInput value={fd.monthly_revenue} onChange={(v) => update({ form_data: { monthly_revenue: v } })} />
            </Field>
            <Field label={t("Средние расходы в месяц, ₽")} hint={t("аренда, зарплаты, закупки, налоги")}>
              <MoneyInput value={fd.monthly_expenses} onChange={(v) => update({ form_data: { monthly_expenses: v } })} />
            </Field>
            <Field label={t("Платежи по текущим кредитам, ₽/мес")} hint={t("0, если кредитов нет")}>
              <MoneyInput value={fd.existing_payments} onChange={(v) => update({ form_data: { existing_payments: v } })} />
            </Field>
            <Field label={t("Сотрудников")}>
              <input className="input" type="number" min={0} value={fd.employees ?? ""} onChange={(e) => update({ form_data: { employees: Number(e.target.value) } })} />
            </Field>
            <Field label={t("Доля крупнейшего клиента в выручке, %")}>
              <input className="input" type="number" min={0} max={100} value={fd.top_client_share ?? ""} onChange={(e) => update({ form_data: { top_client_share: Number(e.target.value) } })} />
            </Field>
          </div>
          {fd.monthly_revenue > 0 && (
            <div className="grid g3">
              <div className="stat"><div className="label">{t("Свободный поток в месяц")}</div><div className={`value ${net > 0 ? "" : "neg"}`}>{money(net)}</div></div>
              <div className="stat"><div className="label">{t("Платёж по новому кредиту")}</div><div className="value">{money(payment)}</div></div>
              <div className="stat">
                <div className="label">{t("Нагрузка всех кредитов")}</div>
                <div className={`value ${burden == null || burden > 0.5 ? "neg" : "pos"}`}>{burden == null ? "—" : `${Math.round(burden * 100)}%`}</div>
              </div>
            </div>
          )}
          {app.statement && (
            <div className="alert info small">
              
              {t("📊 По загруженной выписке очищенные поступления —")} {money(app.statement.avg_monthly_inflow)}  {t("в месяц.")}{" "}
              {Math.abs((fd.monthly_revenue ?? 0) - app.statement.avg_monthly_inflow) > app.statement.avg_monthly_inflow * 0.15 && (
                <button className="link" onClick={() => update({ form_data: { monthly_revenue: app.statement.avg_monthly_inflow } })}>{t("Подставить в анкету")}</button>
              )}
            </div>
          )}
          {burden != null && burden > 0.5 && (
            <div className="alert warn">{t("Платежи забирают больше половины свободного потока — банк может предложить меньшую сумму или больший срок. Вернитесь на шаг «Параметры», чтобы подобрать комфортный платёж.")}</div>
          )}
        </div>
      )}

      {step === 3 && (
        <div className="card stack">
          {requiredCodes.length === 0 && <div className="alert ok">{t("Для этой заявки обязательных документов нет 🎉 Сведения о компании банк получит из ЕГРЮЛ, ФНС и БКИ.")}</div>}
          {requiredCodes.map((c) => <DocUpload key={c} app={app} code={c} label={docLabel(c)} required onUploaded={(a) => { version.current = a.version; setApp(a); }} />)}
          {app.statement && (
            <StatementCard s={app.statement} declared={fd.monthly_revenue} onApplyRevenue={(v) => update({ form_data: { monthly_revenue: v } })} />
          )}
          <h3 className="mt">{t("По желанию — ускорят рассмотрение")}</h3>
          {OPTIONAL_DOCS.filter((c) => !requiredCodes.includes(c)).map((c) => (
            <DocUpload key={c} app={app} code={c} label={docLabel(c)} onUploaded={(a) => { version.current = a.version; setApp(a); }} />
          ))}
          <SampleStatements />
        </div>
      )}

      {step === 4 && (
        <div className="card stack lg">
          <h3>{t("Проверьте заявку")}</h3>
          <dl className="kv">
            <dt>{t("Продукт")}</dt><dd>{product?.name ?? t("не выбран")}</dd>
            <dt>{t("Сумма и срок")}</dt><dd>{money(app.amount)}  {t("на")} {months(app.term_months)}</dd>
            <dt>{t("Цель")}</dt><dd>{catalog.purposes.find((p) => p.code === app.purpose)?.label ?? "—"}</dd>
            <dt>{t("Ориентировочный платёж")}</dt><dd>{money(payment)}  {t("/ мес")}</dd>
            <dt>{t("Выручка / расходы")}</dt><dd>{money(fd.monthly_revenue)} / {money(fd.monthly_expenses)}</dd>
            <dt>{t("Залог")}</dt><dd>{app.has_collateral ? app.collateral_description || t("да") : t("нет")}</dd>
            <dt>{t("Документы")}</dt><dd>{app.documents.length ? app.documents.map((d) => d.label).join(", ") : "—"}</dd>
          </dl>
          <div className="stack">
            <label className="check">
              <input type="checkbox" checked={!!app.consents.personal_data} onChange={(e) => update({ consents: { personal_data: e.target.checked } })} />
              
              {t("Согласен на обработку персональных данных для рассмотрения заявки")}
            </label>
            <label className="check">
              <input type="checkbox" checked={!!app.consents.bki} onChange={(e) => update({ consents: { bki: e.target.checked } })} />
              
              {t("Согласен на запрос кредитной истории компании и руководителя в бюро кредитных историй")}
            </label>
          </div>
          <ErrorBox error={errors} />
          <div className="row">
            <button className="btn primary" onClick={submit}>{t("Отправить заявку в банк")}</button>
            <span className="small muted">{t("После отправки я буду показывать каждый этап проверки в реальном времени")}</span>
          </div>
        </div>
      )}

      <div className="row between">
        <button className="btn ghost" disabled={step === 0} onClick={() => { flush(); setStep(step - 1); }}>{t("← Назад")}</button>
        {step < STEPS.length - 1 && <button className="btn dark" onClick={() => { flush(); setStep(step + 1); }}>{t("Далее →")}</button>}
      </div>
    </div>
  );
}
