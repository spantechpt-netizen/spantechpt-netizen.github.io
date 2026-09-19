-- Span Tech CRM — database schema
-- Engine: SQLite (node:sqlite). All money is stored as REAL in the quotation currency.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT    NOT NULL,
  name_ar       TEXT,
  email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT    NOT NULL,
  role          TEXT    NOT NULL DEFAULT 'engineer',  -- admin | manager | engineer | viewer
  title         TEXT,
  title_ar      TEXT,
  phone         TEXT,
  country       TEXT    DEFAULT 'SA',
  lang          TEXT    NOT NULL DEFAULT 'ar',
  active        INTEGER NOT NULL DEFAULT 1,
  last_login_at TEXT,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT    NOT NULL,
  ip         TEXT,
  user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- ---------------------------------------------------------------- customers
CREATE TABLE IF NOT EXISTS customers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT    UNIQUE,
  name_en     TEXT    NOT NULL,
  name_ar     TEXT,
  type        TEXT    NOT NULL DEFAULT 'main_contractor',
  country     TEXT    NOT NULL DEFAULT 'SA',   -- SA | EG | QA
  city        TEXT,
  sector      TEXT,                            -- residential | commercial | education | healthcare | industrial | infrastructure | mixed
  website     TEXT,
  phone       TEXT,
  email       TEXT,
  address     TEXT,
  tax_number  TEXT,
  cr_number   TEXT,
  status      TEXT    NOT NULL DEFAULT 'target', -- target | prospect | active | dormant | blacklisted
  source      TEXT,                              -- referral | website | exhibition | cold_call | existing | tender | social
  rating      INTEGER NOT NULL DEFAULT 3,        -- 1..5 priority of the target
  owner_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  notes       TEXT,
  created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_customers_country ON customers(country);
CREATE INDEX IF NOT EXISTS idx_customers_status  ON customers(status);
CREATE INDEX IF NOT EXISTS idx_customers_owner   ON customers(owner_id);

CREATE TABLE IF NOT EXISTS contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  name        TEXT    NOT NULL,
  name_ar     TEXT,
  title       TEXT,
  phone       TEXT,
  mobile      TEXT,
  email       TEXT,
  is_primary  INTEGER NOT NULL DEFAULT 0,
  notes       TEXT,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts(customer_id);

-- ------------------------------------------------------------ opportunities
CREATE TABLE IF NOT EXISTS opportunities (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT    UNIQUE,
  title          TEXT    NOT NULL,
  title_ar       TEXT,
  customer_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  contact_id     INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
  country        TEXT    NOT NULL DEFAULT 'SA',
  city           TEXT,
  project_type   TEXT,                            -- tower | school | mall | villa | rest_house | admin | hospital | parking | other
  area_sqm       REAL    NOT NULL DEFAULT 0,
  stage          TEXT    NOT NULL DEFAULT 'new',  -- new | qualified | quoted | negotiation | won | lost
  probability    INTEGER NOT NULL DEFAULT 10,     -- 0..100
  expected_value REAL    NOT NULL DEFAULT 0,
  currency       TEXT    NOT NULL DEFAULT 'SAR',
  expected_close TEXT,
  source         TEXT,
  owner_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  lost_reason    TEXT,                            -- price | timing | competitor | scope | no_budget | no_response | other
  lost_to        TEXT,
  notes          TEXT,
  closed_at      TEXT,
  created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_opps_stage    ON opportunities(stage);
CREATE INDEX IF NOT EXISTS idx_opps_customer ON opportunities(customer_id);
CREATE INDEX IF NOT EXISTS idx_opps_owner    ON opportunities(owner_id);
CREATE INDEX IF NOT EXISTS idx_opps_country  ON opportunities(country);

-- --------------------------------------------------- activities / reminders
CREATE TABLE IF NOT EXISTS activities (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  type           TEXT    NOT NULL DEFAULT 'call',  -- call | meeting | email | whatsapp | site_visit | task | note
  subject        TEXT    NOT NULL,
  notes          TEXT,
  customer_id    INTEGER REFERENCES customers(id) ON DELETE CASCADE,
  opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE CASCADE,
  quotation_id   INTEGER REFERENCES quotations(id) ON DELETE CASCADE,
  contact_id     INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
  owner_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  due_at         TEXT,
  done           INTEGER NOT NULL DEFAULT 0,
  done_at        TEXT,
  outcome        TEXT,
  created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_activities_due   ON activities(done, due_at);
CREATE INDEX IF NOT EXISTS idx_activities_owner ON activities(owner_id);
CREATE INDEX IF NOT EXISTS idx_activities_cust  ON activities(customer_id);
CREATE INDEX IF NOT EXISTS idx_activities_opp   ON activities(opportunity_id);

-- --------------------------------------------------------------- quotations
CREATE TABLE IF NOT EXISTS quotations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  number           TEXT    NOT NULL,            -- SPAN TECH P.T - 26 - 059
  revision         INTEGER NOT NULL DEFAULT 0,
  parent_id        INTEGER REFERENCES quotations(id) ON DELETE SET NULL,
  opportunity_id   INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
  customer_id      INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  contact_id       INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
  project_name     TEXT    NOT NULL,
  project_name_ar  TEXT,
  location         TEXT,
  location_ar      TEXT,
  attention        TEXT,
  attention_ar     TEXT,
  subject_en       TEXT,
  subject_ar       TEXT,
  country          TEXT    NOT NULL DEFAULT 'SA',
  currency         TEXT    NOT NULL DEFAULT 'SAR',
  vat_rate         REAL    NOT NULL DEFAULT 15,
  vat_included     INTEGER NOT NULL DEFAULT 0,  -- 0 = prices exclude VAT
  issue_date       TEXT    NOT NULL DEFAULT (date('now')),
  valid_days       INTEGER NOT NULL DEFAULT 10,
  status           TEXT    NOT NULL DEFAULT 'draft',
  -- cost model inputs (note 2 of the printed offer)
  strand_price_ton REAL    NOT NULL DEFAULT 4000,
  strand_kg_sqm    REAL    NOT NULL DEFAULT 3.5,
  anchors_per_ton  REAL    NOT NULL DEFAULT 25,
  anchor_cost      REAL    NOT NULL DEFAULT 0,
  duct_cost_sqm    REAL    NOT NULL DEFAULT 0,
  grout_cost_sqm   REAL    NOT NULL DEFAULT 0,
  labour_cost_sqm  REAL    NOT NULL DEFAULT 0,
  design_cost_sqm  REAL    NOT NULL DEFAULT 0,
  overhead_pct     REAL    NOT NULL DEFAULT 0,
  target_margin    REAL    NOT NULL DEFAULT 0,
  price_variance   REAL    NOT NULL DEFAULT 5,   -- ± % re-negotiation trigger
  -- totals (computed server side, never trusted from the client)
  subtotal         REAL    NOT NULL DEFAULT 0,
  discount_type    TEXT    NOT NULL DEFAULT 'none', -- none | percent | amount
  discount_value   REAL    NOT NULL DEFAULT 0,
  discount_amount  REAL    NOT NULL DEFAULT 0,
  net_amount       REAL    NOT NULL DEFAULT 0,
  vat_amount       REAL    NOT NULL DEFAULT 0,
  total            REAL    NOT NULL DEFAULT 0,
  cost_total       REAL    NOT NULL DEFAULT 0,
  margin_amount    REAL    NOT NULL DEFAULT 0,
  margin_pct       REAL    NOT NULL DEFAULT 0,
  -- editable document content
  scope_json         TEXT,   -- { design:[], supply:[], installation:[], deliverables:[], requirements:[] }
  payment_terms_json TEXT,   -- [ { pct, label_en, label_ar } ]
  conditions_json    TEXT,   -- [ { en, ar } ]
  notes_en           TEXT,
  notes_ar           TEXT,
  intro_en           TEXT,
  intro_ar           TEXT,
  owner_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
  sent_at          TEXT,
  decided_at       TEXT,
  reject_reason    TEXT,
  created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (number, revision)
);
CREATE INDEX IF NOT EXISTS idx_quotes_customer ON quotations(customer_id);
CREATE INDEX IF NOT EXISTS idx_quotes_status   ON quotations(status);
CREATE INDEX IF NOT EXISTS idx_quotes_owner    ON quotations(owner_id);
CREATE INDEX IF NOT EXISTS idx_quotes_date     ON quotations(issue_date);

CREATE TABLE IF NOT EXISTS quotation_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  quotation_id INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  desc_en      TEXT    NOT NULL,
  desc_ar      TEXT,
  unit_en      TEXT    NOT NULL DEFAULT 'm²',
  unit_ar      TEXT    NOT NULL DEFAULT 'م²',
  qty          REAL    NOT NULL DEFAULT 0,
  unit_price   REAL    NOT NULL DEFAULT 0,
  amount       REAL    NOT NULL DEFAULT 0,
  is_optional  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_quote ON quotation_items(quotation_id);

-- ------------------------------------------------------ settings and audit
CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS counters (
  key   TEXT    PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  entity      TEXT NOT NULL,
  entity_id   INTEGER,
  action      TEXT NOT NULL,
  detail_json TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_time   ON audit_log(created_at);

-- ====================================================== notifications & inbox
-- One row per recipient. `dedupe_key` stops the reminder sweep raising the
-- same alert twice (a unique index enforces it per user).
CREATE TABLE IF NOT EXISTS notifications (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  actor_id    INTEGER REFERENCES users(id) ON DELETE SET NULL, -- NULL = raised by the system
  type        TEXT    NOT NULL,   -- message | assigned | activity_due | activity_overdue
                                  -- | stale_customer | quote_status | quote_expiring | quote_expired
  title_ar    TEXT    NOT NULL,
  title_en    TEXT    NOT NULL,
  body_ar     TEXT,
  body_en     TEXT,
  entity      TEXT,               -- customer | opportunity | quotation | activity | message
  entity_id   INTEGER,
  link        TEXT,               -- client-side route, e.g. "quote/12"
  severity    TEXT    NOT NULL DEFAULT 'info',  -- info | warning | danger
  is_read     INTEGER NOT NULL DEFAULT 0,
  read_at     TEXT,
  dedupe_key  TEXT,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_dedupe
  ON notifications(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

-- Internal messages between engineers. `parent_id` threads a reply onto the
-- message it answers; the root message carries the subject.
CREATE TABLE IF NOT EXISTS messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id  INTEGER REFERENCES messages(id) ON DELETE CASCADE,
  sender_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject    TEXT,
  body       TEXT    NOT NULL,
  entity     TEXT,               -- optionally pinned to a customer / opportunity / quotation
  entity_id  INTEGER,
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);

CREATE TABLE IF NOT EXISTS message_recipients (
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  is_read    INTEGER NOT NULL DEFAULT 0,
  read_at    TEXT,
  PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_msg_recipients_user ON message_recipients(user_id, is_read);

-- ================================================================ email intake
-- Company mailboxes the CRM reads. The password is stored encrypted; see
-- server/secrets.js. Read-only access is enough — nothing is ever sent or
-- deleted, and messages are fetched with BODY.PEEK so the inbox stays unread.
CREATE TABLE IF NOT EXISTS mail_accounts (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  label             TEXT    NOT NULL,
  host              TEXT    NOT NULL,
  port              INTEGER NOT NULL DEFAULT 993,
  secure            INTEGER NOT NULL DEFAULT 1,   -- 1 = implicit TLS (993), 0 = STARTTLS (143)
  username          TEXT    NOT NULL,
  password_enc      TEXT    NOT NULL,
  folders           TEXT    NOT NULL DEFAULT '["INBOX"]',
  active            INTEGER NOT NULL DEFAULT 1,
  sync_minutes      INTEGER NOT NULL DEFAULT 10,
  last_sync_at      TEXT,
  last_error        TEXT,
  state_json        TEXT,    -- { "INBOX": { uidValidity, lastUid } }
  created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mail_messages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id       INTEGER NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
  folder           TEXT    NOT NULL DEFAULT 'INBOX',
  uid              INTEGER NOT NULL,
  message_id       TEXT,
  in_reply_to      TEXT,
  from_email       TEXT,
  from_name        TEXT,
  to_emails        TEXT,
  subject          TEXT,
  body_text        TEXT,
  snippet          TEXT,
  received_at      TEXT,
  has_attachments  INTEGER NOT NULL DEFAULT 0,
  attachments_json TEXT,
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (account_id, folder, uid)
);
CREATE INDEX IF NOT EXISTS idx_mail_msg_from ON mail_messages(from_email);
CREATE INDEX IF NOT EXISTS idx_mail_msg_date ON mail_messages(received_at);

-- One row per email that looks like it needs action. The manager triages these
-- and hands each to an engineer; converting one creates the customer and the
-- opportunity from the extracted data.
CREATE TABLE IF NOT EXISTS mail_requests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id      INTEGER NOT NULL REFERENCES mail_messages(id) ON DELETE CASCADE,
  status          TEXT    NOT NULL DEFAULT 'new',  -- new | assigned | converted | dismissed
  kind            TEXT    NOT NULL DEFAULT 'rfq',  -- rfq | reply | other
  confidence      INTEGER NOT NULL DEFAULT 0,
  extraction_json TEXT,
  summary_ar      TEXT,
  summary_en      TEXT,
  customer_id     INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  opportunity_id  INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
  quotation_id    INTEGER REFERENCES quotations(id) ON DELETE SET NULL,
  assigned_to     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  assigned_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  assigned_at     TEXT,
  handled_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  handled_at      TEXT,
  notes           TEXT,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (message_id)
);
CREATE INDEX IF NOT EXISTS idx_mail_req_status ON mail_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_mail_req_assignee ON mail_requests(assigned_to);

-- Drawings attached to a cost study: the original design the owner already has,
-- and the post-tensioned tender drawings we produced from it. Files live on
-- disk under data/uploads; this table is the index.
CREATE TABLE IF NOT EXISTS study_drawings (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  quotation_id  INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
  kind          TEXT    NOT NULL DEFAULT 'original', -- original | post_tension
  caption_ar    TEXT,
  caption_en    TEXT,
  filename      TEXT    NOT NULL,   -- as stored on disk, never client-supplied
  original_name TEXT,
  content_type  TEXT    NOT NULL,
  bytes         INTEGER NOT NULL DEFAULT 0,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  uploaded_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  -- Every table carries this: the generic update() helper writes it on any row
  -- it touches, and without it captioning a drawing fails outright.
  updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_study_drawings_quote ON study_drawings(quotation_id, kind, sort_order);
