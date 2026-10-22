import { lang, t } from "./i18n";

const TOKEN_KEY = "alfa_credit_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* приватный режим — токен живёт до перезагрузки */
  }
}

export class ApiError extends Error {
  status: number;
  errors: string[];
  constructor(status: number, message: string, errors: string[] = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const msgs = detail.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg ?? ""}`);
    return new ApiError(status, t("Проверьте введённые данные"), msgs);
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; errors?: string[] };
    return new ApiError(status, d.message ?? t("Ошибка"), d.errors ?? []);
  }
  return new ApiError(status, status >= 500 ? t("Сервис временно недоступен") : t("Ошибка запроса"));
}

type Opts = { method?: string; body?: unknown; form?: FormData };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  // Язык интерфейса — сервер переводит тексты кабинета клиента (каталог, статусы, Альфик)
  const headers: Record<string, string> = { "X-Lang": lang };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && token) {
    setToken(null);
    window.location.href = "/login";
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw parseError(res.status, data);
  return data as T;
}
