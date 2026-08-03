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
