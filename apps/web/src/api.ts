const API_URL_KEY = "gitseek:api-base-url";
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "") ?? "";

export type ApiHealth = {
  status: "ok";
  service: string;
  version?: string;
  environment?: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly kind: "network" | "rate_limit" | "server" | "request",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/$/, "");
  if (!trimmed) return "";
  const parsed = new URL(trimmed);
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error("API 地址必须以 http:// 或 https:// 开头");
  }
  return trimmed;
}

export function getDefaultApiBaseUrl(): string {
  return configuredApiBaseUrl;
}

export function getApiBaseUrl(): string {
  try {
    const saved = localStorage.getItem(API_URL_KEY);
    return saved === null ? configuredApiBaseUrl : saved;
  } catch {
    return configuredApiBaseUrl;
  }
}

export function setApiBaseUrl(value: string): string {
  const normalized = normalizeApiBaseUrl(value);
  localStorage.setItem(API_URL_KEY, normalized);
  return normalized;
}

export function resetApiBaseUrl(): string {
  localStorage.removeItem(API_URL_KEY);
  return configuredApiBaseUrl;
}

export function apiUrl(path: string, baseUrl = getApiBaseUrl()): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl.replace(/\/$/, "")}${normalizedPath}`;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string; message?: string };
    return payload.detail || payload.message || `请求失败（HTTP ${response.status}）`;
  } catch {
    return `请求失败（HTTP ${response.status}）`;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit, baseUrl?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path, baseUrl), init);
  } catch {
    throw new ApiError("无法连接 GitSeek 服务，请检查网络或后端地址。", null, "network");
  }
  if (!response.ok) {
    const message = await errorMessage(response);
    if (response.status === 429) throw new ApiError(message, response.status, "rate_limit");
    if (response.status >= 500) throw new ApiError(message, response.status, "server");
    throw new ApiError(message, response.status, "request");
  }
  return response.json() as Promise<T>;
}

export async function checkApiHealth(baseUrl = getApiBaseUrl()): Promise<ApiHealth> {
  return apiFetch<ApiHealth>("/health", { headers: { Accept: "application/json" } }, baseUrl);
}
