CREATE TABLE IF NOT EXISTS kgs_versions (
  law TEXT NOT NULL, version TEXT NOT NULL, effective_date TEXT NOT NULL,
  expected INTEGER NOT NULL, release_hash TEXT NOT NULL,
  PRIMARY KEY (law, version)
);
CREATE TABLE IF NOT EXISTS kgs_active (
  law TEXT PRIMARY KEY, version TEXT, blocked_version TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kgs_docs (
  id INTEGER PRIMARY KEY, law TEXT NOT NULL, version TEXT NOT NULL, seq INTEGER NOT NULL,
  article TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, ref TEXT NOT NULL, bg TEXT NOT NULL,
  UNIQUE (law, version, seq)
);
-- 기존 FTS에 음수 ID로 추가해 국내외 법령과 동일한 점수로 검색한다.
CREATE TRIGGER IF NOT EXISTS kgs_docs_insert AFTER INSERT ON kgs_docs BEGIN
  INSERT INTO docs_fts(rowid, bg) VALUES (-new.id, new.bg);
END;
CREATE TRIGGER IF NOT EXISTS kgs_docs_delete AFTER DELETE ON kgs_docs BEGIN
  INSERT INTO docs_fts(docs_fts, rowid, bg) VALUES ('delete', -old.id, old.bg);
END;
