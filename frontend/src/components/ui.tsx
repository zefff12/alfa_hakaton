import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import { STATUS_TONE, num, parseNum } from "../format";
import type { Catalog } from "../types";

export const ALFIK = {
  sit: "/alfik/alfik-sit.png",
  wave: "/alfik/alfik-wave.png",
  notes: "/alfik/alfik-notes.png",
};

export function AlfikSay({ children, pose = "sit", size, soft }: {
  children: ReactNode; pose?: keyof typeof ALFIK; size?: "sm" | "lg"; soft?: boolean;
}) {
  return (
    <div className={`alfik-say ${size ?? ""}`}>
      <img src={ALFIK[pose]} alt="Альфик" className="bob" />
      <div className={`bubble ${soft ? "soft" : ""}`}>
        <b className="name">Альфик</b>
        {children}
      </div>
    </div>
  );
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return <span className={`badge ${STATUS_TONE[status] ?? "neutral"}`}>{label}</span>;
}

export function MoneyInput({ value, onChange, big, placeholder }: {
  value: number | null | undefined; onChange: (v: number) => void; big?: boolean; placeholder?: string;
}) {
  const show = (v: number | null | undefined) => (v ? num(v) : "");
  const [text, setText] = useState(show(value));
  useEffect(() => {
    if (parseNum(text) !== (value ?? 0)) setText(show(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <input
      className={`input ${big ? "big" : ""}`}
      inputMode="numeric"
      placeholder={placeholder ?? "0"}
      value={text}
      onChange={(e) => {
        const raw = e.target.value.replace(/[^\d\s]/g, "");
        setText(raw);
        onChange(parseNum(raw));
      }}
      onBlur={() => setText(show(parseNum(text)))}
    />
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

export function ErrorBox({ error }: { error: any }) {
  if (!error) return null;
  return (
    <div className="alert bad">
      {error.message ?? String(error)}
      {error.errors?.length > 0 && (
        <ul>{error.errors.map((e: string) => <li key={e}>{e}</li>)}</ul>
      )}
    </div>
  );
}

let catalogCache: Catalog | null = null;
export function useCatalog(): Catalog | null {
  const [c, setC] = useState<Catalog | null>(catalogCache);
  useEffect(() => {
    if (!catalogCache) api<Catalog>("/api/catalog").then((d) => { catalogCache = d; setC(d); });
  }, []);
  return c;
}

export function Track({ steps, current, failed }: { steps: string[]; current: number; failed?: boolean }) {
  return (
    <div className="track">
      {steps.map((s, i) => (
        <div key={s} className={`track-step ${i < current ? "done" : ""} ${i === current ? (failed ? "bad" : "current") : ""}`}>
          <div className="dot">{i < current ? "✓" : i === current && failed ? "!" : i + 1}</div>
          <span>{s}</span>
        </div>
      ))}
    </div>
  );
}

export function Gauge({ value, label }: { value: number; label?: string }) {
  const angle = Math.PI * (1 - value / 100);
  const x = 110 + 90 * Math.cos(angle);
  const y = 115 - 90 * Math.sin(angle);
  const color = value >= 70 ? "#0f9d58" : value >= 45 ? "#f2a100" : "#ef3124";
  return (
    <div className="gauge">
      <svg viewBox="0 0 220 130">
        <path d="M20 115 A90 90 0 0 1 200 115" fill="none" stroke="#eef0f3" strokeWidth="18" strokeLinecap="round" />
        <path d={`M20 115 A90 90 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}`} fill="none" stroke={color} strokeWidth="18" strokeLinecap="round" />
      </svg>
      <div className="val">{value}<small>{label ?? "из 100"}</small></div>
    </div>
  );
}

export function FactorList({ factors }: { factors: { code: string; name: string; value: string; points: number; explanation: string }[] }) {
  const max = Math.max(60, ...factors.map((f) => Math.abs(f.points)));
  return (
    <div>
      {factors.map((f) => (
        <div className="factor" key={f.code}>
          <div>
            <b>{f.name}</b> <span className="muted small">· {f.value}</span>
            <div className="small muted">{f.explanation}</div>
          </div>
          <div className="bar">
            <div style={{
              left: f.points >= 0 ? "50%" : `${50 - (Math.abs(f.points) / max) * 50}%`,
              width: `${(Math.abs(f.points) / max) * 50}%`,
              background: f.points >= 0 ? "var(--ok)" : "var(--bad)",
            }} />
            <div style={{ left: "50%", width: 2, background: "#c9ced6" }} />
          </div>
          <div className={`pts ${f.points > 0 ? "pos" : f.points < 0 ? "neg" : ""}`}>{f.points > 0 ? "+" : ""}{f.points}</div>
        </div>
      ))}
    </div>
  );
}

export function Loader({ text = "Загружаю…" }: { text?: string }) {
  return <div className="empty"><img src={ALFIK.sit} alt="" className="bob" /><p>{text}</p></div>;
}
