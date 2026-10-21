import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AlfikSay, Loader } from "../components/ui";

const KIND: Record<string, string> = { news: "Новость", tip: "Совет", offer: "Предложение", guide: "Гид" };
const STAGE: Record<string, string> = {
  none: "заявок пока нет", draft: "заполняете заявку", in_review: "заявка на рассмотрении", info_requested: "банк ждёт документы",
  offer: "есть предложение банка", rejected: "был отказ", borrower: "действующий заёмщик",
};

export default function Feed() {
  const [feed, setFeed] = useState<any>(null);
  const [liked, setLiked] = useState<Set<string>>(new Set());
  const nav = useNavigate();
  const load = () => api("/api/feed").then(setFeed);
  useEffect(() => { load(); }, []);
  if (!feed) return <Loader />;

  const react = async (item_id: string, action: string) => {
    await api("/api/feed/react", { body: { item_id, action } });
    if (action === "like") setLiked(new Set([...liked, item_id]));
    load();
  };

  return (
    <div className="stack lg">
      <div className="page-head">
        <div><h1>Лента Альфика</h1><p>Новости, советы и предложения, подобранные под ваш бизнес и этап заявки</p></div>
      </div>
      <AlfikSay pose="notes">
        Я подстраиваю ленту под вас: отрасль — <b>{feed.profile.industry_label}</b>, сейчас — <b>{STAGE[feed.profile.stage]}</b>.
        Лента меняется, когда меняется статус заявки, а скрытые карточки я больше не покажу.
      </AlfikSay>
      <div className="grid g2">
        {feed.items.map((it: any) => (
          <div className="feed-card" key={it.id}>
            <div className="row between">
              <span className="feed-kind">{KIND[it.kind]}</span>
              <span className="small muted">релевантность {it.score}</span>
            </div>
            <h3>{it.title}</h3>
            <p className="muted">{it.body}</p>
            <div className="why">💡 {it.why}</div>
            <div className="row mt">
              {it.cta && <button className="btn dark sm" onClick={() => { react(it.id, "open"); nav(it.cta.to); }}>{it.cta.label}</button>}
              <button className="btn ghost sm" onClick={() => react(it.id, "like")} disabled={liked.has(it.id)}>{liked.has(it.id) ? "♥ Полезно" : "♡ Полезно"}</button>
              <button className="btn ghost sm" onClick={() => react(it.id, "hide")}>Не интересно</button>
            </div>
          </div>
        ))}
      </div>
      <p className="small muted">Контент ленты демонстрационный и сформирован для прототипа.</p>
    </div>
  );
}
