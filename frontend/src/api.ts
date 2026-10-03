let currentSession = "";
let currentSpace = "default";
let expired = false;
function expireSession() { expired = true; window.dispatchEvent(new Event("resumedetective:space-expired")); }
export async function verifySession(): Promise<void> {
  if (!currentSession || expired) return;
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) return;
    const info = await response.json() as { session?: string };
    if (info.session && info.session !== currentSession) expireSession();
  } catch { /* The service may briefly restart; do not adopt a new session. */ }
}
export async function initializeSession(): Promise<void> {
  if (currentSession) return;
  const response = await fetch("/api/health", { cache: "no-store" });
  if (!response.ok) throw new Error("无法连接本地服务");
  const info = await response.json() as { session?: string; spaceId?: string };
  currentSession = info.session || ""; currentSpace = info.spaceId || "default";
}
export const resumeURL = (id: number) => `/resume/${id}?session=${encodeURIComponent(currentSession)}`;
export const spaceDownloadURL = (name: string) => `/api/spaces/backups/${encodeURIComponent(name)}?session=${encodeURIComponent(currentSession)}`;
export const spacePreferenceKey = (key: string) => `${key}:space:${currentSpace}`;

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (expired) throw new Error("当前页面属于旧空间，请刷新后再操作");
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (currentSession) headers.set("X-ResumeDetective-Session", currentSession);
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
  });
  const session = response.headers.get("X-ResumeDetective-Session");
  if (currentSession && session && session !== currentSession) {
    expireSession();
    throw new Error("空间或服务已切换；本页面已停止操作，请刷新。旧页面没有写入数据。");
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const value = await response.json();
      if (value?.error) message = value.error;
    } catch {
      // Keep the safe generic message for non-JSON failures.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const jsonBody = (value: unknown): RequestInit => ({ body: JSON.stringify(value) });

export function formatDateTime(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 16);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export const todayISO = () => {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
};
