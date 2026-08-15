import { ApiError } from "../api";
import type { Recommendation, SearchResponse } from "../types";
import type { SavedEntry, SearchHistoryEntry, SearchOptions, SearchProblem, View } from "./types";

export const DEFAULT_SEARCH_OPTIONS: SearchOptions = {
  purpose: "learning",
  weeklyHours: null,
  platform: null,
  licenses: [],
  recentOnly: false,
  projectSize: null,
};

export const SAVED_ENTRIES_KEY = "gitseek:saved-entries";
export const SEARCH_HISTORY_KEY = "gitseek:search-history";

export const sampleQueries = [
  "适合初学者的 FastAPI 项目，MIT 许可证，最近半年活跃",
  "每周 5 小时，第一次贡献 AI 工具项目",
  "Windows 可运行、无需 GPU 的中文 OCR 项目",
];

export const navItems: { id: View; label: string }[] = [
  { id: "discover", label: "搜索" },
  { id: "saved", label: "收藏" },
];

export function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function getDeviceId() {
  const key = "gitseek:device-id";
  const existing = localStorage.getItem(key) || localStorage.getItem("openscout:device-id");
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(key, created);
  return created;
}

export function readSavedEntries(): SavedEntry[] {
  try {
    const detailed = JSON.parse(localStorage.getItem(SAVED_ENTRIES_KEY) ?? "[]") as SavedEntry[];
    if (Array.isArray(detailed) && detailed.length) return detailed.filter((item) => item?.repository?.includes("/"));
    const legacy = JSON.parse(localStorage.getItem("gitseek:saved") ?? localStorage.getItem("openscout:saved") ?? "[]") as string[];
    return Array.isArray(legacy)
      ? legacy.filter((item) => typeof item === "string" && item.includes("/")).map((repository) => ({ repository, savedAt: null, snapshot: null }))
      : [];
  } catch {
    return [];
  }
}

export function persistSavedEntries(entries: SavedEntry[]) {
  localStorage.setItem(SAVED_ENTRIES_KEY, JSON.stringify(entries));
  localStorage.setItem("gitseek:saved", JSON.stringify(entries.map((item) => item.repository)));
}

export function readSearchHistory(): SearchHistoryEntry[] {
  try {
    const history = JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) ?? "[]") as SearchHistoryEntry[];
    return Array.isArray(history) ? history.filter((item) => item?.query && item?.options).slice(0, 8) : [];
  } catch {
    return [];
  }
}

export function persistSearchHistory(entries: SearchHistoryEntry[]) {
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(entries));
}

export function savedEntryAsRecommendation(entry: SavedEntry): Recommendation {
  if (entry.snapshot) return entry.snapshot;
  return {
    rank: 0,
    full_name: entry.repository,
    description: "此前收藏的 GitHub 项目。打开档案后会重新读取公开仓库信息。",
    html_url: `https://github.com/${entry.repository}`,
    score: 0,
    stars: 0,
    language: null,
    license_spdx: null,
    pushed_at: null,
    constraint_match: {},
    score_breakdown: {},
    reasons: ["已收藏到当前设备"],
    risks: [],
  };
}

export function problemFrom(error: unknown): SearchProblem {
  if (error instanceof ApiError) {
    if (error.kind === "rate_limit") return { kind: error.kind, title: "GitHub 请求暂时达到限额", message: "稍等几分钟再试，或检查云端 GITHUB_TOKEN 是否仍然有效。" };
    if (error.kind === "network") return { kind: error.kind, title: "没有连接到 GitSeek 服务", message: "请检查网络，或在应用设置中确认后端地址。" };
    if (error.kind === "server") return { kind: error.kind, title: "云端服务暂时没有完成请求", message: error.message };
    return { kind: error.kind, title: "请求没有被服务接受", message: error.message };
  }
  return { kind: "network", title: "没有连接到 GitSeek 服务", message: "请检查网络，或在应用设置中确认后端地址。" };
}

export function emptySearchResponse(query: string, options: SearchOptions, pushedAfter: string | null): SearchResponse {
  return {
    session_id: "",
    query,
    generated_github_query: "",
    constraints: {
      purpose: options.purpose,
      language: "未确定",
      technologies: [],
      licenses: options.licenses,
      exclude_archived: true,
      pushed_after: pushedAfter,
      weekly_hours: options.weeklyHours,
      platform: options.platform,
      project_size: options.projectSize,
    },
    source_total_count: 0,
    eligible_candidate_count: 0,
    ranking_version: "hybrid-vector-v9",
    results: [],
    retrieval: { local_candidates: 0, github_candidates: 0, github_status: "unavailable", index_freshest_at: null },
  };
}
