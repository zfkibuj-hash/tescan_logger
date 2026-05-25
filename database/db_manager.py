"""Database manager with schema, WAL mode, and thread-local connections.

Handles both main database (sessions, users, settings) and separate HV database.
GLP compliant: no hard deletes of raw data, audit trail on all modifications.
"""

import sqlite3
import threading
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAIN_SCHEMA = """
-- Microscopes: type is immutable after creation
CREATE TABLE IF NOT EXISTS microscopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    serial_number TEXT UNIQUE NOT NULL,
    microscope_type TEXT NOT NULL CHECK(microscope_type IN ('VEGA3', 'MIRA3_FEG')),
    location TEXT DEFAULT '',
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Users / operators
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'operator' CHECK(role IN ('admin', 'operator')),
    discount_percent REAL DEFAULT 0.0,
    excluded_from_billing INTEGER DEFAULT 0,
    pin_hash TEXT,
    email TEXT,
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Billing tier rates per microscope
CREATE TABLE IF NOT EXISTS billing_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    tier_name TEXT NOT NULL CHECK(tier_name IN ('PROJECT', 'UJ_UNIT', 'EXTERNAL')),
    rate_pln_per_hour REAL NOT NULL DEFAULT 150.0,
    UNIQUE(microscope_id, tier_name)
);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    microscope_type TEXT NOT NULL,
    username TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'COMPLETE'
        CHECK(status IN ('COMPLETE', 'PARTIAL_SESSION', 'INCOMPLETE_CONTEXT', 'CANCELLED')),
    billing_tier TEXT DEFAULT 'PROJECT'
        CHECK(billing_tier IN ('PROJECT', 'UJ_UNIT', 'EXTERNAL')),
    hourly_rate REAL DEFAULT 150.0,
    rate_override REAL,
    discount_percent REAL DEFAULT 0.0,
    calculated_cost REAL DEFAULT 0.0,
    cost_override REAL,
    time_override_minutes REAL,
    excluded_from_invoice INTEGER DEFAULT 0,
    cancelled INTEGER DEFAULT 0,
    hv_on_time TEXT,
    hv_off_time TEXT,
    gvl_open_time TEXT,
    gvl_close_time TEXT,
    notes TEXT,
    source_file TEXT,
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Vacuum cycles
CREATE TABLE IF NOT EXISTS vacuum_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    session_id INTEGER REFERENCES sessions(id),
    username TEXT,
    command TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL DEFAULT 0.0,
    status TEXT DEFAULT 'IN_PROGRESS'
        CHECK(status IN ('OK', 'ABORTED', 'LEFT_VENTED', 'IN_PROGRESS')),
    ready_time_seconds REAL,
    source_file TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Penalties (LEFT_VENTED = 100 PLN)
CREATE TABLE IF NOT EXISTS penalties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacuum_cycle_id INTEGER REFERENCES vacuum_cycles(id),
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    username TEXT NOT NULL,
    amount REAL DEFAULT 100.0,
    reason TEXT DEFAULT 'LEFT_VENTED',
    timestamp TEXT,
    paid INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Anomalies
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    session_id INTEGER REFERENCES sessions(id),
    anomaly_type TEXT NOT NULL,
    severity TEXT DEFAULT 'warning' CHECK(severity IN ('info', 'warning', 'critical')),
    timestamp TEXT,
    description TEXT,
    value REAL,
    threshold REAL,
    source_file TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Pressure events from HV analysis
CREATE TABLE IF NOT EXISTS pressure_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL REFERENCES microscopes(id),
    session_id INTEGER REFERENCES sessions(id),
    timestamp TEXT,
    pressure_type TEXT DEFAULT 'chamber',
    pressure_value_pa REAL,
    baseline_pa REAL,
    spike_factor REAL,
    duration_seconds REAL,
    source_file TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Settings (key-value)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- File cache for incremental import
CREATE TABLE IF NOT EXISTS file_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER,
    file_type TEXT,
    imported_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    record_count INTEGER DEFAULT 0
);

-- Parser errors
CREATE TABLE IF NOT EXISTS parser_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT,
    line_number INTEGER,
    raw_line TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Audit log (GLP compliant, UTC timestamps)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    changed_by TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    description TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_microscope ON sessions(microscope_id);
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_tier ON sessions(billing_tier);
CREATE INDEX IF NOT EXISTS idx_vacuum_microscope ON vacuum_cycles(microscope_id);
CREATE INDEX IF NOT EXISTS idx_vacuum_session ON vacuum_cycles(session_id);
CREATE INDEX IF NOT EXISTS idx_penalties_username ON penalties(username);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_file_cache_path ON file_cache(file_path);
"""

HV_SCHEMA = """
-- HV samples (separate database for performance)
CREATE TABLE IF NOT EXISTS hv_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microscope_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    source_file TEXT,
    set_hv_kv REAL DEFAULT 0.0,
    actual_hv_kv REAL DEFAULT 0.0,
    emission_current_ua REAL DEFAULT 0.0,
    filament_current_a REAL DEFAULT 0.0,
    gun_pressure_pa REAL DEFAULT 0.0,
    chamber_pressure_pa REAL DEFAULT 0.0,
    heating_percent REAL,
    gun_valve_state TEXT,
    extractor_voltage_kv REAL,
    suppressor_voltage_v REAL,
    total_current_ua REAL,
    flags_hex TEXT,
    column_ion_pump_pressure_pa REAL
);

CREATE INDEX IF NOT EXISTS idx_hv_timestamp ON hv_samples(timestamp);
CREATE INDEX IF NOT EXISTS idx_hv_microscope ON hv_samples(microscope_id);
CREATE INDEX IF NOT EXISTS idx_hv_microscope_time ON hv_samples(microscope_id, timestamp);
"""

# Default settings
DEFAULT_SETTINGS = {
    "data_retention_years": "5",
    "backup_on_startup": "true",
    "backup_retention_days": "30",
    "default_billing_tier": "PROJECT",
    "penalty_amount_pln": "100.0",
    "heatmap_colors": '[{"value": 0, "color": "#FFFFFF"}, {"value": 0.01, "color": "#00FF00"}, {"value": 1.0, "color": "#FF0000"}]',
    "current_user": "",
    "require_pin": "false",
}


class DatabaseManager:
    """Thread-safe SQLite database manager with WAL mode.

    Manages two databases:
    - Main DB: sessions, users, settings, audit
    - HV DB: high-frequency HV/emission samples (separate for performance)
    """

    def __init__(self, db_path: str = "tescan_logger.db", hv_db_path: str = "tescan_hv.db"):
        self.db_path = db_path
        self.hv_db_path = hv_db_path
        self._local = threading.local()
        self._hv_local = threading.local()
        self._lock = threading.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection to main database."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=30)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _get_hv_connection(self) -> sqlite3.Connection:
        """Get thread-local connection to HV database."""
        if not hasattr(self._hv_local, 'conn') or self._hv_local.conn is None:
            self._hv_local.conn = sqlite3.connect(self.hv_db_path, timeout=30)
            self._hv_local.conn.row_factory = sqlite3.Row
            self._hv_local.conn.execute("PRAGMA journal_mode=WAL")
            self._hv_local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._hv_local.conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Main database connection (thread-local)."""
        return self._get_connection()

    @property
    def hv_conn(self) -> sqlite3.Connection:
        """HV database connection (thread-local)."""
        return self._get_hv_connection()

    def initialize(self) -> None:
        """Create all tables and insert default settings."""
        logger.info("Initializing main database: %s", self.db_path)
        self.conn.executescript(MAIN_SCHEMA)
        self.conn.commit()

        logger.info("Initializing HV database: %s", self.hv_db_path)
        self.hv_conn.executescript(HV_SCHEMA)
        self.hv_conn.commit()

        # Insert default settings if not present
        for key, value in DEFAULT_SETTINGS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        self.conn.commit()
        logger.info("Database initialization complete")

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value by key."""
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row["value"]
        return default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (key, value)
        )
        self.conn.commit()

    def close(self) -> None:
        """Close all thread-local connections."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
        if hasattr(self._hv_local, 'conn') and self._hv_local.conn:
            self._hv_local.conn.close()
            self._hv_local.conn = None

    def verify_integrity(self) -> dict:
        """Verify database integrity (GLP compliance check).

        Returns dict with:
        - integrity_ok: bool
        - audit_coverage: bool (all modified entities have audit entries)
        - issues: list of strings describing problems
        """
        issues = []

        # SQLite integrity check
        result = self.conn.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = result[0] == "ok"
        if not integrity_ok:
            issues.append(f"SQLite integrity check failed: {result[0]}")

        # Check audit coverage: sessions with version > 1 should have audit entries
        orphan_sessions = self.conn.execute("""
            SELECT s.id FROM sessions s
            WHERE s.version > 1
            AND NOT EXISTS (
                SELECT 1 FROM audit_log a
                WHERE a.entity_type = 'session' AND a.entity_id = s.id
            )
        """).fetchall()
        audit_coverage = len(orphan_sessions) == 0
        if not audit_coverage:
            issues.append(
                f"Found {len(orphan_sessions)} sessions with edits but no audit trail"
            )

        # HV DB integrity
        hv_result = self.hv_conn.execute("PRAGMA integrity_check").fetchone()
        if hv_result[0] != "ok":
            issues.append(f"HV database integrity check failed: {hv_result[0]}")
            integrity_ok = False

        return {
            "integrity_ok": integrity_ok,
            "audit_coverage": audit_coverage,
            "issues": issues,
        }
