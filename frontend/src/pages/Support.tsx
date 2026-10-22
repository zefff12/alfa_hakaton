import { useNavigate } from "react-router-dom";
import { FileText, Gauge, Layers, MessageCircle, Mic, ShieldCheck } from "lucide-react";
import { openAlfik } from "../components/Chat";
import { t } from "../i18n";

const FAQ = [
  t("Какой кредит мне подойдёт?"),
  t("Какие нужны документы?"),
  t("Какой статус заявки?"),
  t("Каковы мои шансы?"),
  t("Платёж слишком высокий"),
  t("Что такое овердрафт?"),
];

export default function Support() {
  const nav = useNavigate();
  return (
    <div className="stack lg">
      <section className="hero">
        <div>
          <span className="badge red">{t("Поддержка 24/7")}</span>
          <h1 style={{ marginTop: 12 }}>{t("Чем помочь?")}</h1>
          <p>{t("Альфик отвечает на вопросы о кредитах, документах и статусе заявки. Если вопрос сложный — передаст его специалисту банка.")}</p>
          <div className="row mt">
            <button className="btn primary" onClick={() => openAlfik()}><MessageCircle size={18} />{t("Написать Альфику")}</button>
            <button className="btn ghost" onClick={() => nav("/talk")}><Mic size={18} />{t("Рассказать голосом")}</button>
          </div>
        </div>
        <img src="/brand/alfik-jump.webp" alt={t("Альфик")} className="bob" />
      </section>
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card stack">
          <h2>{t("Частые вопросы")}</h2>
          {FAQ.map((q) => (
            <button key={q} className="faq-item" onClick={() => openAlfik(q)}><span className="fq"><MessageCircle size={18} /></span>{q}</button>
          ))}
        </div>
        <div className="grid" style={{ gap: 12 }}>
          {[
            { icon: Layers, title: t("Кредитный подбор"), text: t("Листайте предложения и сохраняйте подходящие"), to: "/match" },
            { icon: Gauge, title: t("Мои шансы"), text: t("Оценка готовности до подачи заявки"), to: "/precheck" },
            { icon: FileText, title: t("Документы"), text: t("Проверка документов и анкеты на ошибки"), to: "/documents" },
            { icon: ShieldCheck, title: t("Безопасность"), text: t("Данные синтетические, договор подписывается кодом в кабинете"), to: "/applications" },
          ].map((x) => (
            <button key={x.title} className="action-tile" onClick={() => nav(x.to)}>
              <x.icon size={26} className="cyan" /><b>{x.title}</b><span>{x.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
