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
};

export type SearchResponse = {
  query: string;
  generated_github_query: string;
  constraints: {
    language: string;
    technologies: string[];
    licenses: string[];
    exclude_archived: boolean;
    pushed_after: string | null;
  };
  source_total_count: number;
  eligible_candidate_count: number;
  ranking_version: string;
  results: Recommendation[];
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
