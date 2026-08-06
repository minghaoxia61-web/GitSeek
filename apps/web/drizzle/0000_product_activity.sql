CREATE TABLE IF NOT EXISTS search_sessions (
  id TEXT PRIMARY KEY,
  query TEXT NOT NULL,
  constraints_json TEXT NOT NULL,
  github_query TEXT NOT NULL,
  source_total_count INTEGER NOT NULL DEFAULT 0,
  eligible_candidate_count INTEGER NOT NULL DEFAULT 0,
  ranking_version TEXT NOT NULL,
  created_at TEXT NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  repository TEXT NOT NULL,
  rank INTEGER NOT NULL,
  score REAL NOT NULL,
  payload_json TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES search_sessions(id) ON DELETE CASCADE,
  UNIQUE(session_id, rank)
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_recommendations_session_id
ON recommendations(session_id);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS repository_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repository TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_repository_snapshots_repository
ON repository_snapshots(repository, fetched_at);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  repository TEXT NOT NULL,
  action TEXT NOT NULL,
  reason TEXT,
  query TEXT,
  device_id TEXT,
  received_at TEXT NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_feedback_action ON feedback(action);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_feedback_device_id ON feedback(device_id);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS saved_repositories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  repository TEXT NOT NULL,
  saved_at TEXT NOT NULL,
  UNIQUE(device_id, repository)
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_saved_repositories_device
ON saved_repositories(device_id, saved_at);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS contribution_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repository TEXT NOT NULL,
  issue_number INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  UNIQUE(repository, issue_number)
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_contribution_issues_repository
ON contribution_issues(repository, fetched_at);
