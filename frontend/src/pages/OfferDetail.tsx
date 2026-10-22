import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, BadgePercent, Calendar, CalendarCheck, CircleCheck, CircleHelp, Clock, FileText, Heart, Layers, Shield,
  ShieldCheck, Sparkles, Target, Wallet, Zap, type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { openAlfik } from "../components/Chat";
import { favoritesChanged } from "../components/Layout";
import { ErrorBox, Loader } from "../components/ui";
import { money, months } from "../format";
import { t } from "../i18n";
import { productArt, productIcon, type MatchOffer } from "../types";
import { useApplyOffer } from "./Favorites";

interface Detail {
  offer: MatchOffer;
  tags: string[];
  in_favorites: boolean;
  conditions: { icon: string; title: string; text: string }[];
  documents: string[];
  advantages: string[];
}

const COND_ICON: Record<string, LucideIcon> = { target: Target, layers: Layers, shield: Shield, clock: Clock, calendar: CalendarCheck };
const TAG_ICON: Record<string, LucideIcon> = {};
const ADV_ICON = [Zap, ShieldCheck, Sparkles, CircleCheck];

export default function OfferDetail() {
  const { code } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState<Detail | null>(null);
  const [amount, setAmount] = useState<number | null>(null);
  const [term, setTerm] = useState<number | null>(null);
  const [error, setError] = useState<any>(null);
  const { apply, busy, error: applyError } = useApplyOffer();

  useEffect(() => {
    const q = amount && term ? `?amount=${amount}&term=${term}` : "";
    const timer = setTimeout(() => {
      api<Detail>(`/api/offers/${code}${q}`).then((x) => {
        setD(x);
        if (amount == null) { setAmount(x.offer.amount); setTerm(x.offer.term_months); }
      }).catch(setError);
    }, amount == null ? 0 : 200);
    return () => clearTimeout(timer);
  }, [code, amount, term]);

  if (!d) return error ? <ErrorBox error={error} /> : <Loader />;
  const o = d.offer;

  const toggleFav = async () => {
    try {
      await api(`/api/favorites/${o.code}`, { method: d.in_favorites ? "DELETE" : "POST" });
      setD({ ...d, in_favorites: !d.in_favorites });
      favoritesChanged();
    } catch (e) { setError(e); }
  };

  return (
    <div className="stack lg">
      <div className="detail-hero">
        <button className="crumb" onClick={() => nav(-1)}><ArrowLeft size={18} />{t("К списку предложений")}</button>
        <div className="row nowrap" style={{ gap: 18, alignItems: "flex-start" }}>
          <div className="sc-icon" style={{ width: 76, height: 76 }}><img src={productIcon(o.code)} alt="" style={{ width: 66, height: 66 }} /></div>
          <div>
            <h1>{o.name}</h1>
            <p className="text-2" style={{ fontSize: 18, marginTop: 6 }}>{o.description}</p>
          </div>
        </div>
        <div className="tag-row mt">
          {d.tags.map((tag) => {
            const Icon = TAG_ICON[tag] ?? (tag === d.tags[0] && o.recommended ? CircleCheck : Sparkles);
            return <span key={tag} className={`tag ${o.recommended && tag === d.tags[0] ? "rec" : ""}`}><Icon size={16} />{tag}</span>;
          })}
        </div>
        <img className="art" src={productArt(o.code)} alt="" />
      </div>

      <div className="grid g3">
        <div className="stat accent icon-stat"><span className="ico"><Wallet className="cyan" /></span><div><div className="label">{t("Сумма кредита")}</div><div className="value">{t("до {0}", money(o.max_amount))}</div></div></div>
        <div className="stat accent icon-stat"><span className="ico"><Calendar className="cyan" /></span><div><div className="label">{t("Срок кредита")}</div><div className="value">{t("до {0}", months(o.max_term))}</div></div></div>
        <div className="stat accent icon-stat"><span className="ico"><BadgePercent className="cyan" /></span><div><div className="label">{t("Процентная ставка")}</div><div className="value">{t("от {0}%", o.rate)}</div></div></div>
      </div>

      <ErrorBox error={error ?? applyError} />

      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card glow stack lg">
          <h2>{t("Пример расчёта")}</h2>
          <div className="stack">
            <div className="slider-row"><span className="text-2">{t("Сумма кредита")}</span><b>{money(amount ?? o.amount)}</b></div>
            <input type="range" min={o.min_amount} max={o.max_amount} step={50_000} value={amount ?? o.amount} onChange={(e) => setAmount(Number(e.target.value))} aria-label={t("Сумма кредита")} />
            <div className="row between small muted"><span>{money(o.min_amount)}</span><span>{money(o.max_amount)}</span></div>
          </div>
          <div className="stack">
            <div className="slider-row"><span className="text-2">{t("Срок кредита")}</span><b>{months(term ?? o.term_months)}</b></div>
            <input type="range" min={o.min_term} max={o.max_term} step={1} value={term ?? o.term_months} onChange={(e) => setTerm(Number(e.target.value))} aria-label={t("Срок кредита")} />
            <div className="row between small muted"><span>{months(o.min_term)}</span><span>{months(o.max_term)}</span></div>
          </div>
          <div className="grid g2">
            <div className="stat accent"><div className="label">{o.revolving ? t("Проценты в месяц (макс.)") : t("Ежемесячный платёж")}</div><div className="value">{money(o.monthly_payment)}</div></div>
            <div className="stat"><div className="label">{t("Переплата")}</div><div className="value">{money(o.total_interest)}</div></div>
          </div>
          <p className="muted small">{t("Расчёт предварительный и не является офертой. Итоговые условия — после рассмотрения заявки.")}</p>
        </div>

        <div className="card stack">
          <h2>{t("Основные условия")}</h2>
          {d.conditions.map((c) => {
            const Icon = COND_ICON[c.icon] ?? CircleCheck;
            return (
              <div key={c.title} className="cond">
                <span className="ci"><Icon size={20} className="cyan" /></span>
                <div><b>{c.title}</b><span>{c.text}</span></div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="row">
        <button className="btn primary lg" disabled={!!busy} onClick={() => apply(o.code, amount ?? undefined, term ?? undefined)}>{busy ? t("Создаю…") : t("Оформить заявку")}</button>
        <button className={`btn lg ${d.in_favorites ? "cyan" : "ghost"}`} onClick={toggleFav}>
          <Heart size={20} fill={d.in_favorites ? "currentColor" : "none"} />{d.in_favorites ? t("В избранном") : t("Добавить в избранное")}
        </button>
      </div>

      <div className="grid g3" style={{ alignItems: "start" }}>
        <div className="card stack">
          <h3>{t("Какие документы нужны?")}</h3>
          {d.documents.map((doc) => <div key={doc} className="row nowrap small"><FileText size={18} className="cyan" style={{ flexShrink: 0 }} />{doc}</div>)}
        </div>
        <div className="card stack">
          <h3>{t("Преимущества")}</h3>
          {d.advantages.map((a, i) => {
            const Icon = ADV_ICON[i % ADV_ICON.length];
            return <div key={a} className="row nowrap small"><Icon size={18} className="cyan" style={{ flexShrink: 0 }} />{a}</div>;
          })}
        </div>
        <div className="card stack">
          <h3>{t("Почему подходит именно вам")}</h3>
          {o.fits.map((f) => <div key={f} className="row nowrap small"><CircleCheck size={18} className="pos" style={{ flexShrink: 0 }} />{f}</div>)}
          {o.gaps.map((g) => <div key={g} className="row nowrap small muted"><CircleHelp size={18} style={{ flexShrink: 0, color: "var(--warn)" }} />{g}</div>)}
          <button className="btn ghost sm" style={{ alignSelf: "flex-start" }} onClick={() => openAlfik(t("Расскажи подробнее про «{0}»", o.name))}>{t("Задать вопрос Альфику")}</button>
        </div>
      </div>
    </div>
  );
}
