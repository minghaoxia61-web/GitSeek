export type View = "discover" | "results" | "detail" | "compare" | "evals";

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
  };
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
  generated_at: string;
  metrics: Array<{
    key: string;
    label: string;
    value: number;
    unit: string;
    target: number;
    passed: boolean;
  }>;
  failures: Array<{ case: string; expected: string; actual: string }>;
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
  };
  evidence: InvestigationEvidence[];
  risks: string[];
  limitations: string[];
};
