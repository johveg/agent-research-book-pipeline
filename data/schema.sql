PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'daily',
  summary_path TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  query TEXT,
  url TEXT,
  title TEXT,
  publisher TEXT,
  author TEXT,
  published_at TEXT,
  captured_at TEXT NOT NULL,
  archived_path TEXT,
  content_hash TEXT,
  reliability_tier TEXT DEFAULT 'unknown',
  quality_score TEXT DEFAULT 'unknown',
  quality_notes TEXT,
  visibility TEXT DEFAULT 'public_or_search_result',
  run_id TEXT,
  UNIQUE(url, content_hash)
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  summary TEXT,
  confidence TEXT DEFAULT 'low',
  first_seen_at TEXT,
  last_seen_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  claim_text TEXT NOT NULL,
  claim_type TEXT DEFAULT 'observation',
  subject_entity_id TEXT,
  confidence TEXT DEFAULT 'low',
  status TEXT DEFAULT 'candidate',
  first_seen_at TEXT,
  last_seen_at TEXT,
  current_best_understanding TEXT,
  evidence_strength TEXT DEFAULT 'weak',
  source_count INTEGER DEFAULT 0,
  editor_notes TEXT,
  reviewed_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entity_sources (
  entity_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  mention_count INTEGER DEFAULT 1,
  first_seen_at TEXT,
  last_seen_at TEXT,
  sample TEXT,
  PRIMARY KEY (entity_id, source_id),
  FOREIGN KEY (entity_id) REFERENCES entities(id),
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS claim_sources (
  claim_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  quote TEXT,
  support_type TEXT DEFAULT 'supports',
  PRIMARY KEY (claim_id, source_id),
  FOREIGN KEY (claim_id) REFERENCES claims(id),
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS relationships (
  id TEXT PRIMARY KEY,
  subject_entity_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  object_entity_id TEXT NOT NULL,
  confidence TEXT DEFAULT 'low',
  first_seen_at TEXT,
  last_seen_at TEXT,
  status TEXT DEFAULT 'observed'
);

CREATE TABLE IF NOT EXISTS trend_terms (
  id TEXT PRIMARY KEY,
  term TEXT NOT NULL,
  term_type TEXT NOT NULL,
  count INTEGER NOT NULL,
  first_seen_at TEXT,
  last_seen_at TEXT,
  status TEXT DEFAULT 'candidate',
  evidence_path TEXT,
  run_id TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS source_notes (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  note TEXT NOT NULL,
  note_type TEXT DEFAULT 'summary',
  created_at TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS editorial_reviews (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  review_type TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT,
  report_path TEXT,
  created_at TEXT NOT NULL
);
