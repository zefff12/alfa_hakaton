import { useRef, useState } from "react";
import { api } from "../api";
import type { Application } from "../types";

export default function DocUpload({ app, code, label, required, onUploaded }: {
  app: Application; code: string; label: string; required?: boolean; onUploaded: (a: Application) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const docs = app.documents.filter((d) => d.doc_type === code);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("doc_type", code);
    form.append("file", file);
    try {
      onUploaded(await api<Application>(`/api/applications/${app.id}/documents`, { form }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className={`upload ${docs.length ? "has" : ""}`}>
      <span style={{ fontSize: 22 }}>{docs.length ? "✅" : "📎"}</span>
      <div style={{ flex: 1, minWidth: 200 }}>
        <b>{label}</b> {required && !docs.length && <span className="badge warn">нужен</span>}
        {docs.map((d) => (
          <div key={d.id} className="small muted">
            {d.filename} · {(d.size_bytes / 1024).toFixed(0)} КБ
            {d.status === "ACCEPTED" && <span className="badge ok" style={{ marginLeft: 6 }}>принят</span>}
            {d.status === "REJECTED" && <span className="badge bad" style={{ marginLeft: 6 }}>отклонён — загрузите заново</span>}
          </div>
        ))}
        {error && <div className="small neg">{error}</div>}
      </div>
      <input ref={ref} type="file" accept=".pdf,.jpg,.jpeg,.png,.txt,.csv,.xlsx,.docx"
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      <button className="btn ghost sm" disabled={busy} onClick={() => ref.current?.click()}>
        {busy ? "Загружаю…" : docs.length ? "Заменить" : "Загрузить"}
      </button>
    </div>
  );
}
