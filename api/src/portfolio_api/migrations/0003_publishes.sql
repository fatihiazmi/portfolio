-- Publish log for the admin Dashboard "last publish". Spec section 9.2, plan T16.
-- One row per deploy hook call. `ok = 0` rows keep the error text.

CREATE TABLE publishes (
  id         INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  ok         INTEGER NOT NULL CHECK (ok IN (0, 1)),
  deploy_id  TEXT,
  error      TEXT
);

CREATE INDEX idx_publishes_created ON publishes (ok, created_at);
