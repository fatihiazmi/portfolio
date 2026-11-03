-- Schema from docs/spec.md section 8.

CREATE TABLE projects (
  id           INTEGER PRIMARY KEY,
  slug         TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  client       TEXT,
  kind         TEXT NOT NULL CHECK (kind IN ('client', 'personal')),
  year         INTEGER,
  summary      TEXT NOT NULL,
  problem_md   TEXT,
  built_md     TEXT,
  decisions_md TEXT,
  outcome_md   TEXT,
  stack        TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(stack) AND json_type(stack) = 'array'),
  repo_url     TEXT,
  diagram_key  TEXT,
  map_x        REAL,
  map_z        REAL,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  published    INTEGER NOT NULL DEFAULT 0 CHECK (published IN (0, 1)),
  updated_at   TEXT NOT NULL
);

CREATE TABLE project_edges (
  from_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  to_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label   TEXT,
  PRIMARY KEY (from_id, to_id),
  CHECK (from_id <> to_id)
);

CREATE TABLE project_images (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  r2_key     TEXT NOT NULL,
  alt        TEXT NOT NULL,
  caption    TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  scrubbed   INTEGER NOT NULL DEFAULT 0 CHECK (scrubbed IN (0, 1))
);

CREATE INDEX idx_project_images_project ON project_images (project_id, sort_order);

CREATE TABLE leads (
  id         INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  name       TEXT NOT NULL,
  email      TEXT NOT NULL,
  company    TEXT,
  kind       TEXT NOT NULL CHECK (kind IN ('freelance', 'hiring', 'other')),
  budget     TEXT,
  message    TEXT NOT NULL,
  ip_hash    TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'replied', 'closed'))
);

CREATE INDEX idx_leads_created ON leads (created_at);
