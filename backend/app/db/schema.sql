CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    game_name TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    result TEXT,
    config_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    topic TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS functional_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    action TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    action TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_text TEXT NOT NULL,
    output_json TEXT,
    success INTEGER NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_text TEXT NOT NULL,
    output_json TEXT,
    success INTEGER NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS config_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    content TEXT NOT NULL
);
