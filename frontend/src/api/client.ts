import { AUTH_EXPIRED, session } from "../lib/session";
import type {
  AuthConfig, BacktestRequest, BacktestResult, BuilderCatalog, LoginResult, StrategyCatalog, SymbolInfo, UiConfig, UploadSpec, UserInfo,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public problems: string[] = [], public status = 0) { super(message); }
}

async function send(url: string, init: RequestInit = {}): Promise<Response> {
  const token = session.token();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { ...init, headers });
  if (res.ok) return res;
  if (res.status === 401 && token) window.dispatchEvent(new Event(AUTH_EXPIRED));
  let detail: unknown;
  try { detail = (await res.json()).detail; } catch { /* non-JSON error */ }
  if (typeof detail === "string") throw new ApiError(detail, [], res.status);
  if (detail && typeof detail === "object" && "message" in detail) {
    const d = detail as { message: string; problems?: string[] };
    throw new ApiError(d.message, d.problems ?? [], res.status);
  }
  throw new ApiError(`Request failed (${res.status})`, [], res.status);
}

const request = async <T>(url: string, init?: RequestInit): Promise<T> => (await send(url, init)).json() as Promise<T>;

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  authConfig: () => request<AuthConfig>("/api/auth/config"),
  requestOtp: (mobile: string) => request<{ sent: boolean; cooldown_seconds: number }>("/api/auth/request-otp", json({ mobile })),
  verifyOtp: (mobile: string, otp: string) => request<LoginResult>("/api/auth/verify-otp", json({ mobile, otp })),
  me: () => request<UserInfo>("/api/auth/me"),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  uiConfig: () => request<UiConfig>("/api/ui-config"),
  symbols: () => request<SymbolInfo[]>("/api/symbols"),
  strategies: () => request<StrategyCatalog>("/api/strategies"),
  ruleBuilder: () => request<BuilderCatalog>("/api/rule-builder"),
  backtest: (req: BacktestRequest) => request<BacktestResult>("/api/backtest", json(req)),

  uploadSpec: () => request<UploadSpec>("/api/admin/upload-spec"),
  upload: (symbol: string, mode: string, file: File) => {
    const form = new FormData();
    form.set("symbol", symbol); form.set("mode", mode); form.set("file", file);
    return request<SymbolInfo>("/api/admin/datasets", { method: "POST", body: form });
  },
  remove: (symbol: string) => request<{ deleted: string }>(`/api/admin/datasets/${encodeURIComponent(symbol)}`, { method: "DELETE" }),
  downloadTemplate: async () => {
    const blob = await (await send("/api/admin/template.csv")).blob();
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "prices_template.csv" });
    a.click();
    URL.revokeObjectURL(a.href);
  },
};
