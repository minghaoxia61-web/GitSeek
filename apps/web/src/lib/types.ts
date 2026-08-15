import type { AgentRunResponse, Recommendation, SearchResponse, View } from "../types";

export type SearchOptions = {
  purpose: "learning" | "contribution";
  weeklyHours: number | null;
  platform: string | null;
  licenses: string[];
  recentOnly: boolean;
  projectSize: "small" | "medium" | "large" | null;
};

export type ConnectionStatus = {
  state: "checking" | "online" | "offline";
  label: string;
  detail: string;
  embeddingConfigured?: boolean;
  embeddingModel?: string | null;
};

export type SearchProblem = {
  kind: "network" | "rate_limit" | "server" | "request";
  title: string;
  message: string;
};

export type SearchAttempt =
  | { kind: "base"; response: SearchResponse }
  | { kind: "agent"; run: AgentRunResponse }
  | { kind: "base-error"; error: unknown }
  | { kind: "agent-error"; error: unknown };

export type RepositoryIndexStatus = {
  repository_count: number;
  snapshot_count: number;
  freshest_at: string | null;
  oldest_at: string | null;
  stale_repository_count: number;
  expired_repository_count: number;
  freshness_state: "empty" | "fresh" | "stale" | "expired";
  next_refresh_at: string | null;
  ready: boolean;
  storage_status?: "ready" | "unavailable";
};

export type SavedEntry = {
  repository: string;
  savedAt: string | null;
  snapshot: Recommendation | null;
};

export type SearchHistoryEntry = {
  query: string;
  searchedAt: string;
  resultCount: number;
  options: SearchOptions;
};

export type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export type { View };
