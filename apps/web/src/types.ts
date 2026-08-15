export type View = "discover" | "results" | "saved" | "detail" | "compare" | "evals" | "settings";

export type Recommendation = {
  rank: number;
  full_name: string;
  description: string | null;
  html_url: string;
  score: number;
  stars: number;
  language: string | null;
  license_spdx: string | null;
  pushed_at: string | null;
  constraint_match: Record<string, "MATCH" | "MISMATCH" | "UNKNOWN">;
  score_breakdown: Record<string, number>;
  reasons: string[];
  risks: string[];
  retrieval_sources?: Array<"local_index" | "github_live">;
  data_fetched_at?: string | null;
  data_valid_until?: string | null;
};

export type SearchResponse = {
  session_id: string;
  query: string;
  generated_github_query: string;
  constraints: {
    purpose: "learning" | "contribution";
    language: string;
    technologies: string[];
    licenses: string[];
    exclude_archived: boolean;
    pushed_after: string | null;
    weekly_hours: number | null;
    platform: string | null;
    project_size: "small" | "medium" | "large" | null;
  };
  source_total_count: number;
  eligible_candidate_count: number;
  ranking_version: string;
  results: Recommendation[];
  retrieval?: {
    local_candidates: number;
    github_candidates: number;
    github_status: "live" | "unavailable";
    index_freshest_at: string | null;
    cache_hit?: boolean;
    cached_at?: string | null;
    persistence_status?: "ready" | "unavailable";
    persistence_error?: string | null;
    embedding_status?: "local" | "external" | "unavailable";
    embedding_model?: string | null;
    embedding_cached_repositories?: number;
    embedding_generated_repositories?: number;
  };
};

export type TrendingResponse = {
  range_days: 7 | 30;
  generated_github_query: string;
  results: Recommendation[];
  fetched_at: string;
};

export type AgentStep = {
  node: "parse_query" | "plan_search" | "retrieve_candidates" | "investigate_repositories" | "verify_evidence";
  status: "completed" | "partial" | "failed";
  started_at: string;
  completed_at: string;
  duration_ms: number;
  attempts: number;
  summary: string;
};

export type AgentRunResponse = {
  run_id: string;
  status: "succeeded" | "partial" | "failed";
  created_at: string;
  completed_at: string;
  retry_count: number;
  interpretation: {
    source: "model" | "rules";
    model: string | null;
    summary: string;
    search_terms: string[];
    fallback_reason: string | null;
  };
  search_plan: string[];
  search: SearchResponse;
  investigations: RepositoryInvestigation[];
  verification: Array<{
    full_name: string;
    checked_claims: number;
    supported_claims: number;
    conflicts: string[];
    evidence_ids: string[];
    support_ratio: number;
    confidence: "high" | "medium" | "low";
  }>;
  steps: AgentStep[];
};

export type ContributionIssue = {
  number: number;
  title: string;
  html_url: string;
  labels: string[];
  comments: number;
  updated_at: string;
  difficulty: "easy" | "medium" | "hard";
  score: number;
  reasons: string[];
  risks: string[];
};

export type ContributionIssueResponse = {
  full_name: string;
  fetched_at: string;
  issues: ContributionIssue[];
  limitations: string[];
};

export type EvaluationSummary = {
  version: string;
  dataset_version: string;
  sample_count: number;
  retrieval_dataset_version?: string | null;
  retrieval_case_count?: number;
  relevance_judgment_count?: number;
  generated_at: string;
  metrics: Array<{
    key: string;
    label: string;
    value: number;
    unit: string;
    target: number;
    passed: boolean;
  }>;
  categories?: Array<{
    key: string;
    label: string;
    passed_fields: number;
    total_fields: number;
    accuracy: number;
  }>;
  failures: Array<{ case_id?: string; category?: string; case: string; expected: string; actual: string }>;
};

export type InvestigationEvidence = {
  id: string;
  fact: string;
  value: boolean | number | string;
  source_url: string;
  fetched_at: string;
  confidence: "high" | "medium" | "low";
};

export type RepositoryInvestigation = {
  full_name: string;
  description: string | null;
  html_url: string;
  default_branch: string;
  fetched_at: string;
  confidence: "high" | "medium" | "low";
  signals: {
    has_readme: boolean;
    has_contributing: boolean;
    has_code_of_conduct: boolean;
    has_issue_template: boolean;
    has_pull_request_template: boolean;
    has_security_policy: boolean;
    has_license: boolean;
    has_tests: boolean;
    has_ci: boolean;
    has_pyproject: boolean;
    has_dependency_file: boolean;
    has_docker: boolean;
    readme_has_quickstart: boolean;
  };
  scores: {
    community_health: number;
    documentation: number;
    engineering: number;
    learning_friendliness: number;
    maintenance?: number;
  };
  activity?: {
    releases_sampled: number;
    latest_release_at: string | null;
    median_release_interval_days: number | null;
    pull_requests_sampled: number;
    merged_pull_request_ratio: number | null;
    median_pull_request_resolution_hours: number | null;
    contributors_sampled: number;
    top_contributor_share: number | null;
    contributor_continuity: "distributed" | "concentrated" | "unknown";
  };
  evidence: InvestigationEvidence[];
  risks: string[];
  limitations: string[];
};
