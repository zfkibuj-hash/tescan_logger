"""Repository classes for data access with audit trail."""

import json
import logging
from typing import List, Optional, Dict

from database.db_manager import DatabaseManager
from models.enums import AuditAction, SessionStatus

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common operations."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def _audit(self, cursor, action, entity_type, entity_id, changed_by, old_val="", new_val=""):
        """Write an audit log entry."""
        cursor.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, changed_by, old_value, new_value) VALUES (?,?,?,?,?,?)",
            (action.value, entity_type, entity_id, changed_by, old_val, new_val))


class SessionRepository(BaseRepository):
    """Repository for session data access."""

    def get_all(self, username=None, status=None, start_date=None, end_date=None) -> List[dict]:
        """Get sessions with optional filters."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        if username:
            query += " AND username = ?"
            params.append(username)
        if status:
            query += " AND status = ?"
            params.append(status)
        if start_date:
            query += " AND start_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND start_time <= ?"
            params.append(end_date)
        query += " ORDER BY start_time DESC"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, session_id: int) -> Optional[dict]:
        """Get a single session by ID."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_discount(self, session_id: int, discount_percent: float, changed_by: str) -> bool:
        """Update session discount percent (PPM)."""
        old = self.get_by_id(session_id)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE sessions SET discount_percent = ? WHERE id = ?", (discount_percent, session_id))
            self._audit(cursor, AuditAction.CHANGE_DISCOUNT, "session", session_id, changed_by,
                        json.dumps({"discount_percent": old["discount_percent"]}),
                        json.dumps({"discount_percent": discount_percent}))
        return True

    def override_cost(self, session_id: int, cost: float, changed_by: str) -> bool:
        """Override session cost with fixed amount (PPM)."""
        old = self.get_by_id(session_id)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE sessions SET override_cost = ?, cost = ? WHERE id = ?", (cost, cost, session_id))
            self._audit(cursor, AuditAction.OVERRIDE_COST, "session", session_id, changed_by,
                        json.dumps({"cost": old["cost"]}), json.dumps({"override_cost": cost}))
        return True

    def override_time(self, session_id: int, minutes: float, changed_by: str) -> bool:
        """Override session billable time (PPM)."""
        old = self.get_by_id(session_id)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE sessions SET override_time_minutes = ? WHERE id = ?", (minutes, session_id))
            self._audit(cursor, AuditAction.OVERRIDE_TIME, "session", session_id, changed_by,
                        json.dumps({"override_time_minutes": old["override_time_minutes"]}),
                        json.dumps({"override_time_minutes": minutes}))
        return True

    def cancel_session(self, session_id: int, changed_by: str) -> bool:
        """Cancel a session (cost = 0, status = CANCELLED)."""
        old = self.get_by_id(session_id)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE sessions SET status = ?, cost = 0 WHERE id = ?",
                           (SessionStatus.CANCELLED.value, session_id))
            self._audit(cursor, AuditAction.CANCEL, "session", session_id, changed_by,
                        json.dumps({"status": old["status"], "cost": old["cost"]}),
                        json.dumps({"status": "CANCELLED", "cost": 0}))
        return True

    def exclude_from_billing(self, session_id: int, excluded: bool, changed_by: str) -> bool:
        """Toggle exclude from billing flag."""
        old = self.get_by_id(session_id)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE sessions SET excluded_from_billing = ? WHERE id = ?",
                           (1 if excluded else 0, session_id))
            self._audit(cursor, AuditAction.EXCLUDE_BILLING, "session", session_id, changed_by,
                        json.dumps({"excluded": bool(old["excluded_from_billing"])}),
                        json.dumps({"excluded": excluded}))
        return True


class VacuumRepository(BaseRepository):
    """Repository for vacuum cycle data."""

    def get_all(self, session_id: Optional[int] = None) -> List[dict]:
        """Get vacuum cycles, optionally filtered by session."""
        query = "SELECT * FROM vacuum_cycles"
        params = []
        if session_id is not None:
            query += " WHERE session_id = ?"
            params.append(session_id)
        query += " ORDER BY pump_start DESC"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_by_source_file(self, source_file: str) -> List[dict]:
        """Get vacuum cycles from a specific source file."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM vacuum_cycles WHERE source_file = ? ORDER BY pump_start", (source_file,))
            return [dict(row) for row in cursor.fetchall()]


class UserRepository(BaseRepository):
    """Repository for user management."""

    def get_all(self) -> List[dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM users ORDER BY username")
            return [dict(row) for row in cursor.fetchall()]

    def get_by_username(self, username: str) -> Optional[dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create(self, username: str, display_name: str, changed_by: str) -> int:
        with self.db.get_cursor() as cursor:
            cursor.execute("INSERT INTO users (username, display_name) VALUES (?, ?)", (username, display_name))
            uid = cursor.lastrowid
            self._audit(cursor, AuditAction.ADD_USER, "user", uid, changed_by, "",
                        json.dumps({"username": username, "display_name": display_name}))
            return uid

    def update_discount(self, username: str, discount_percent: float, changed_by: str) -> bool:
        old = self.get_by_username(username)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE users SET discount_percent = ? WHERE username = ?", (discount_percent, username))
            self._audit(cursor, AuditAction.EDIT_USER, "user", old["id"], changed_by,
                        json.dumps({"discount_percent": old["discount_percent"]}),
                        json.dumps({"discount_percent": discount_percent}))
        return True

    def set_excluded(self, username: str, excluded: bool, changed_by: str) -> bool:
        old = self.get_by_username(username)
        if not old:
            return False
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE users SET excluded_from_billing = ? WHERE username = ?",
                           (1 if excluded else 0, username))
            self._audit(cursor, AuditAction.EDIT_USER, "user", old["id"], changed_by,
                        json.dumps({"excluded": bool(old["excluded_from_billing"])}),
                        json.dumps({"excluded": excluded}))
        return True


class HVRepository(BaseRepository):
    """Repository for HV sample data."""

    def get_samples(self, start_time=None, end_time=None, downsample: int = 1) -> List[dict]:
        """Get HV samples with optional time range and downsampling."""
        query = "SELECT * FROM hv_samples WHERE 1=1"
        params = []
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        if downsample > 1:
            query += f" AND (rowid % {downsample}) = 0"
        query += " ORDER BY timestamp"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_sample_count(self, start_time=None, end_time=None) -> int:
        """Count HV samples in a time range."""
        query = "SELECT COUNT(*) as cnt FROM hv_samples WHERE 1=1"
        params = []
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()["cnt"]


class AuditRepository(BaseRepository):
    """Repository for audit log entries."""

    def get_all(self, limit: int = 200, entity_type: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


class FileRepository(BaseRepository):
    """Repository for imported file records."""

    def get_all(self) -> List[dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM file_cache ORDER BY import_date DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, file_id: int) -> Optional[dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM file_cache WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_related_counts(self, file_path: str) -> Dict[str, int]:
        """Get counts of related records for a file."""
        counts = {}
        tables = ["sessions", "vacuum_cycles", "hv_samples", "anomalies", "penalties"]
        with self.db.get_cursor() as cursor:
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE source_file = ?", (file_path,))
                counts[table] = cursor.fetchone()["cnt"]
        return counts


class SettingsRepository(BaseRepository):
    """Repository for application settings."""

    def get(self, key: str, default: str = "") -> str:
        return self.db.get_setting(key, default)

    def set(self, key: str, value: str, changed_by: str = "system") -> None:
        old_value = self.get(key)
        self.db.set_setting(key, value)
        if old_value != value:
            with self.db.get_cursor() as cursor:
                self._audit(cursor, AuditAction.CHANGE_SETTING, "setting", None, changed_by,
                            json.dumps({"key": key, "value": old_value}),
                            json.dumps({"key": key, "value": value}))

    def get_all_settings(self) -> Dict[str, str]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT key, value FROM settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}


class PenaltyRepository(BaseRepository):
    """Repository for penalties."""

    def get_all(self, username=None, source_file=None) -> List[dict]:
        query = "SELECT * FROM penalties WHERE 1=1"
        params = []
        if username:
            query += " AND username = ?"
            params.append(username)
        if source_file:
            query += " AND source_file = ?"
            params.append(source_file)
        query += " ORDER BY timestamp DESC"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


class AnomalyRepository(BaseRepository):
    """Repository for anomalies."""

    def get_all(self, anomaly_type=None, severity=None) -> List[dict]:
        query = "SELECT * FROM anomalies WHERE 1=1"
        params = []
        if anomaly_type:
            query += " AND anomaly_type = ?"
            params.append(anomaly_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY timestamp DESC"
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
