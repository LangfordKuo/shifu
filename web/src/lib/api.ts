/**
 * 极简 API 客户端：自动携带 accessToken，401 时自动刷新一次并重放请求。
 * 后端约定：业务接口前缀 /api（NestJS global prefix）。
 */

const BASE = '/api';

interface ApiResponse<T> {
  ok: boolean;
  status: number;
  data: T;
}

// ---- token 存取（localStorage 持久化，刷新页面不掉线）----
const TOKEN_KEY = 'shifu.tokens';

export interface Tokens {
  accessToken: string;
  refreshToken: string;
}

export function loadTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

export function saveTokens(tokens: Tokens | null) {
  if (tokens) localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(TOKEN_KEY);
}

// ---- 刷新互斥：并发 401 只触发一次 refresh ----
let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const tokens = loadTokens();
  if (!tokens?.refreshToken) return false;
  const resp = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken: tokens.refreshToken }),
  });
  if (!resp.ok) {
    saveTokens(null);
    return false;
  }
  const data = (await resp.json()) as Tokens;
  saveTokens(data);
  return true;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
): Promise<T> {
  const tokens = loadTokens();
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (tokens?.accessToken) headers.Authorization = `Bearer ${tokens.accessToken}`;

  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (resp.status === 401 && retry) {
    refreshing = refreshing ?? refreshTokens().finally(() => (refreshing = null));
    const ok = await refreshing;
    if (ok) return request<T>(method, path, body, false);
    saveTokens(null);
    window.location.href = '/login';
  }

  let data: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!resp.ok) {
    const message =
      (data as { message?: string | string[] })?.message != null
        ? Array.isArray((data as { message: string[] }).message)
          ? (data as { message: string[] }).message.join('；')
          : (data as { message: string }).message
        : `请求失败（${resp.status}）`;
    throw new ApiError(resp.status, message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

export type { ApiResponse };
