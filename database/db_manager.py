"""Database manager with full schema, WAL mode, and initialization."""

import sqlite3
import os
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    discount_percent REAL DEFAULT 0.0,
    excluded_from_billing INTEGER DEFAULT 0,
    pin_hash TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL DEFAULT 0.0,
    gvl_total_seconds REAL DEFAULT 0.0,
    gvl_cycle_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'COMPLETE',
    cost REAL DEFAULT 0.0,
    discount_percent REAL DEFAULT 0.0,
    discount_hours REAL DEFAULT 0.0,
    override_cost REAL,
    override_time_minutes REAL,
    excluded_from_billing INTEGER DEFAULT 0,
    source_file TEXT,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS vacuum_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    pump_start TEXT,
    ready_time TEXT,
    end_time TEXT,
    status TEXT DEFAULT 'IN_PROGRESS',
    pump_duration_seconds REAL DEFAULT 0.0,
    source_file TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS penalties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    vacuum_cycle_id INTEGER,
    penalty_type TEXT DEFAULT 'LEFT_VENTED',
    amount_pln REAL DEFAULT 100.0,
    username TEXT,
    timestamp TEXT,
    source_file TEXT,
    notes TEXT DEFAULT '',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (vacuum_cycle_id) REFERENCES vacuum_cycles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_type TEXT NOT NULL,
    session_id INTEGER,
    timestamp TEXT,
    duration_seconds REAL DEFAULT 0.0,
    severity TEXT DEFAULT 'warning',
    description TEXT DEFAULT '',
    source_file TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS hv_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    set_hv_kv REAL DEFAULT 0.0,
    actual_hv_kv REAL DEFAULT 0.0,
    emission_current_ua REAL DEFAULT 0.0,
    emitter_current_a REAL DEFAULT 0.0,
    heating_percent REAL DEFAULT 0.0,
    gun_pressure_pa REAL DEFAULT 0.0,
    chamber_pressure_pa REAL DEFAULT 0.0,
    gun_valve_state TEXT DEFAULT 'Closed',
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_type TEXT NOT NULL,
    import_date TEXT DEFAULT (datetime('now')),
    record_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS parser_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    line_number INTEGER,
    raw_line TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    changed_by TEXT DEFAULT 'system',
    old_value TEXT DEFAULT '',
    new_value TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'utc'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_source_file ON sessions(source_file);
CREATE INDEX IF NOT EXISTS idx_vacuum_session_id ON vacuum_cycles(session_id);
CREATE INDEX IF NOT EXISTS idx_vacuum_source_file ON vacuum_cycles(source_file);
CREATE INDEX IF NOT EXISTS idx_hv_timestamp ON hv_samples(timestamp);
CREATE INDEX IF NOT EXISTS idx_hv_source_file ON hv_samples(source_file);
CREATE INDEX IF NOT EXISTS idx_anomalies_source_file ON anomalies(source_file);
CREATE INDEX IF NOT EXISTS idx_penalties_source_file ON penalties(source_file);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_file_cache_hash ON file_cache(file_hash);
"""

DEFAULT_SETTINGS = {
    "rate_pln_per_hour": "150.0",
    "pump_time_warning_seconds": "300",
    "pump_time_critical_seconds": "600",
    "idle_after_ready_threshold_seconds": "1800",
    "penalty_left_vented_pln": "100.0",
    "auto_backup_on_start": "1",
    "backup_retention_days": "30",
    "serial_number": "",
}


class DatabaseManager:
    """Manages SQLite database with WAL mode."""

    def __init__(self, db_path: str = "tescan_vega3.db"):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create database, enable WAL mode, and create schema."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA_SQL)
        self._insert_default_settings(conn)
        conn.commit()
        logger.info("Database initialized: %s", self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @contextmanager
    def get_connection(self):
        """Context manager for database connection."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _insert_default_settings(self, conn: sqlite3.Connection) -> None:
        """Insert default settings if they don't exist."""
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value by key."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
