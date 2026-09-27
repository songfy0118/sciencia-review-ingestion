PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS apps (
  app_id TEXT PRIMARY KEY, label TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  app_id TEXT NOT NULL REFERENCES apps(app_id), review_id TEXT NOT NULL,
  content TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
  thumbs_up_count INTEGER NOT NULL CHECK(thumbs_up_count >= 0),
  review_at TEXT NOT NULL, collected_at TEXT NOT NULL,
  review_created_version TEXT, reply_content TEXT, replied_at TEXT,
  PRIMARY KEY(app_id, review_id)
);
CREATE INDEX IF NOT EXISTS review_dates ON reviews(review_at DESC);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, app_id TEXT NOT NULL, label TEXT NOT NULL,
  started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
  pages INTEGER NOT NULL DEFAULT 0, observed INTEGER NOT NULL DEFAULT 0,
  cursor TEXT, warning TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS run_dates ON runs(started_at DESC);
CREATE TABLE IF NOT EXISTS pages (
  run_id TEXT NOT NULL REFERENCES runs(run_id), page INTEGER NOT NULL,
  observed_at TEXT NOT NULL, records_json TEXT NOT NULL,
  PRIMARY KEY(run_id, page)
);
CREATE TABLE IF NOT EXISTS request_limits (
  bucket TEXT PRIMARY KEY, used INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS app_locks (
  app_id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at INTEGER NOT NULL
);
