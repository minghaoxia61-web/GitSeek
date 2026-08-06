CREATE TABLE IF NOT EXISTS repository_index (
  repository TEXT PRIMARY KEY,
  language TEXT,
  license_spdx TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  pushed_at TEXT,
  search_text TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_repository_index_filters
ON repository_index(language, archived, license_spdx, pushed_at);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_repository_index_freshness
ON repository_index(fetched_at);
