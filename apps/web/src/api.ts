import type { AgentRunResponse, AgentStep } from "./types";

const API_URL_KEY = "gitseek:api-base-url";
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "")
  || (import.meta.env.PROD ? "https://git-seek-swart.vercel.app" : "");

export type ApiHealth = {
  status: "ok";
  service: string;
  version?: string;
  environment?: string;
  embedding_configured?: boolean;
  embedding_model?: string | null;
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
    return saved === null || (saved === "" && configuredApiBaseUrl) ? configuredApiBaseUrl : saved;
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

export async function streamAgentRun(
  body: unknown,
  onProgress: (step: AgentStep) => void,
  signal?: AbortSignal,
): Promise<AgentRunResponse> {
  const response = await fetch(apiUrl("/api/v1/agent/runs/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status, response.status === 429 ? "rate_limit" : response.status >= 500 ? "server" : "request");
  }
  if (!response.body) throw new ApiError("服务没有返回可读取的执行流。", 502, "server");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const data = block.match(/^data:\s*(.+)$/m)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data) as AgentStep | AgentRunResponse | { message?: string };
      if (event === "progress") onProgress(payload as AgentStep);
      if (event === "result") return payload as AgentRunResponse;
      if (event === "error") throw new ApiError((payload as { message?: string }).message || "Agent 执行失败", 502, "server");
    }
    if (done) break;
  }
  throw new ApiError("Agent 执行流提前结束。", 502, "server");
}
