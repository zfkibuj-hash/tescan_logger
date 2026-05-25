"""Repository classes for main database entities.

Implements Repository Pattern for clean data access.
All modifications go through audit trail.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict

from models.enums import (
    SessionStatus, MicroscopeType, AuditAction,
    BillingTier, UserRole, VacuumStatus
)
from models.dataclasses import (
    Session, VacuumCycle, User, Microscope, AuditEntry,
    Penalty, BillingTierConfig
)

logger = logging.getLogger(__name__)



class AuditRepository:
    """Repository for audit log entries (GLP compliance)."""

    def __init__(self, db_manager):
        self.db = db_manager

    def log_action(
        self, action: AuditAction, entity_type: str,
        entity_id: Optional[int], changed_by: str,
        old_value=None, new_value=None, description: str = ""
    ) -> None:
        """Record an audit trail entry."""
        self.db.conn.execute(
            """INSERT INTO audit_log
               (action, entity_type, entity_id, changed_by,
                old_value, new_value, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                action.value, entity_type, entity_id, changed_by,
                json.dumps(old_value) if old_value else None,
                json.dumps(new_value) if new_value else None,
                description,
            )
        )
        self.db.conn.commit()

    def get_history(
        self, entity_type: str, entity_id: int
    ) -> List[AuditEntry]:
        """Get audit history for a specific entity."""
        rows = self.db.conn.execute(
            """SELECT * FROM audit_log
               WHERE entity_type = ? AND entity_id = ?
               ORDER BY created_at DESC""",
            (entity_type, entity_id)
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_all(self, limit: int = 100) -> List[AuditEntry]:
        """Get recent audit entries."""
        rows = self.db.conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row) -> AuditEntry:
        return AuditEntry(
            id=row["id"],
            action=AuditAction(row["action"]),
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            changed_by=row["changed_by"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )



class SessionRepository:
    """Repository for Session entities."""

    def __init__(self, db_manager, audit_repo: AuditRepository):
        self.db = db_manager
        self.audit = audit_repo

    def get_by_id(self, session_id: int) -> Optional[Session]:
        """Get session by ID."""
        row = self.db.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def get_all(
        self, microscope_id: Optional[int] = None,
        username: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        start_after: Optional[str] = None,
        start_before: Optional[str] = None,
        limit: int = 500,
    ) -> List[Session]:
        """Get sessions with optional filters."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []

        if microscope_id:
            query += " AND microscope_id = ?"
            params.append(microscope_id)
        if username:
            query += " AND username = ?"
            params.append(username)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if start_after:
            query += " AND start_time >= ?"
            params.append(start_after)
        if start_before:
            query += " AND start_time <= ?"
            params.append(start_before)

        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        rows = self.db.conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_discount(
        self, session_id: int, discount: float, changed_by: str
    ) -> None:
        """Update session discount (reduces time, not rate)."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET discount_percent = ?, version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (discount, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.CHANGE_DISCOUNT, "session", session_id, changed_by,
            {"discount_percent": old.discount_percent},
            {"discount_percent": discount},
        )

    def update_cost_override(
        self, session_id: int, cost: float, changed_by: str
    ) -> None:
        """Set fixed cost override for session."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET cost_override = ?, version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (cost, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.OVERRIDE_COST, "session", session_id, changed_by,
            {"cost_override": old.cost_override},
            {"cost_override": cost},
        )


    def update_time_override(
        self, session_id: int, minutes: float, changed_by: str
    ) -> None:
        """Set time override in minutes."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET time_override_minutes = ?,
               version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (minutes, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.OVERRIDE_TIME, "session", session_id, changed_by,
            {"time_override_minutes": old.time_override_minutes},
            {"time_override_minutes": minutes},
        )

    def update_billing_tier(
        self, session_id: int, tier: BillingTier, changed_by: str
    ) -> None:
        """Change billing tier for session."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET billing_tier = ?,
               version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (tier.value, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.CHANGE_TIER, "session", session_id, changed_by,
            {"billing_tier": old.billing_tier.value},
            {"billing_tier": tier.value},
        )

    def update_rate_override(
        self, session_id: int, rate: float, changed_by: str
    ) -> None:
        """Set rate override PLN/h for session."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET rate_override = ?,
               version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (rate, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.CHANGE_RATE, "session", session_id, changed_by,
            {"rate_override": old.rate_override},
            {"rate_override": rate},
        )

    def cancel_session(self, session_id: int, changed_by: str) -> None:
        """Cancel session (GLP: not deleted, just marked)."""
        old = self.get_by_id(session_id)
        if not old:
            return
        self.db.conn.execute(
            """UPDATE sessions SET cancelled = 1,
               status = 'CANCELLED', version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (session_id,)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.CANCEL, "session", session_id, changed_by,
            {"cancelled": False, "status": old.status.value},
            {"cancelled": True, "status": "CANCELLED"},
        )

    def toggle_exclude_invoice(
        self, session_id: int, changed_by: str
    ) -> None:
        """Toggle excluded_from_invoice flag."""
        old = self.get_by_id(session_id)
        if not old:
            return
        new_val = 0 if old.excluded_from_invoice else 1
        self.db.conn.execute(
            """UPDATE sessions SET excluded_from_invoice = ?,
               version = version + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ?""",
            (new_val, session_id)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.EXCLUDE_INVOICE, "session", session_id, changed_by,
            {"excluded_from_invoice": old.excluded_from_invoice},
            {"excluded_from_invoice": bool(new_val)},
        )

    def _row_to_session(self, row) -> Session:
        """Convert DB row to Session dataclass."""
        return Session(
            id=row["id"],
            microscope_id=row["microscope_id"],
            microscope_type=MicroscopeType(row["microscope_type"]),
            username=row["username"],
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_seconds=row["duration_seconds"] or 0.0,
            status=SessionStatus(row["status"]),
            billing_tier=BillingTier(row["billing_tier"]) if row["billing_tier"] else BillingTier.PROJECT,
            hourly_rate=row["hourly_rate"] or 150.0,
            rate_override=row["rate_override"],
            discount_percent=row["discount_percent"] or 0.0,
            calculated_cost=row["calculated_cost"] or 0.0,
            cost_override=row["cost_override"],
            time_override_minutes=row["time_override_minutes"],
            excluded_from_invoice=bool(row["excluded_from_invoice"]),
            cancelled=bool(row["cancelled"]),
            hv_on_time=datetime.fromisoformat(row["hv_on_time"]) if row["hv_on_time"] else None,
            hv_off_time=datetime.fromisoformat(row["hv_off_time"]) if row["hv_off_time"] else None,
            gvl_open_time=datetime.fromisoformat(row["gvl_open_time"]) if row["gvl_open_time"] else None,
            gvl_close_time=datetime.fromisoformat(row["gvl_close_time"]) if row["gvl_close_time"] else None,
            notes=row["notes"],
            source_file=row["source_file"] or "",
            version=row["version"] or 1,
        )



class VacuumRepository:
    """Repository for VacuumCycle and Penalty entities."""

    def __init__(self, db_manager):
        self.db = db_manager

    def get_cycles(
        self, microscope_id: Optional[int] = None,
        username: Optional[str] = None,
        status: Optional[VacuumStatus] = None,
        limit: int = 500,
    ) -> List[VacuumCycle]:
        """Get vacuum cycles with filters."""
        query = "SELECT * FROM vacuum_cycles WHERE 1=1"
        params = []
        if microscope_id:
            query += " AND microscope_id = ?"
            params.append(microscope_id)
        if username:
            query += " AND username = ?"
            params.append(username)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        rows = self.db.conn.execute(query, params).fetchall()
        return [self._row_to_cycle(r) for r in rows]

    def get_penalties(
        self, username: Optional[str] = None, limit: int = 100
    ) -> List[Penalty]:
        """Get penalties with optional username filter."""
        query = "SELECT * FROM penalties WHERE 1=1"
        params = []
        if username:
            query += " AND username = ?"
            params.append(username)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.db.conn.execute(query, params).fetchall()
        return [self._row_to_penalty(r) for r in rows]

    def _row_to_cycle(self, row) -> VacuumCycle:
        return VacuumCycle(
            id=row["id"],
            microscope_id=row["microscope_id"],
            session_id=row["session_id"],
            username=row["username"],
            command=row["command"],
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_seconds=row["duration_seconds"] or 0.0,
            status=VacuumStatus(row["status"]),
            ready_time_seconds=row["ready_time_seconds"],
            source_file=row["source_file"] or "",
        )

    def _row_to_penalty(self, row) -> Penalty:
        return Penalty(
            id=row["id"],
            vacuum_cycle_id=row["vacuum_cycle_id"],
            microscope_id=row["microscope_id"],
            username=row["username"],
            amount=row["amount"],
            reason=row["reason"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            paid=bool(row["paid"]),
            notes=row["notes"],
        )



class UserRepository:
    """Repository for User entities."""

    def __init__(self, db_manager, audit_repo: AuditRepository):
        self.db = db_manager
        self.audit = audit_repo

    def get_all(self, active_only: bool = True) -> List[User]:
        """Get all users."""
        query = "SELECT * FROM users"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY username"
        rows = self.db.conn.execute(query).fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        row = self.db.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def create(self, user: User, changed_by: str) -> int:
        """Create new user. Returns user ID."""
        cursor = self.db.conn.execute(
            """INSERT INTO users
               (username, display_name, role, discount_percent,
                excluded_from_billing, pin_hash, email, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user.username, user.display_name, user.role.value,
             user.discount_percent, int(user.excluded_from_billing),
             user.pin_hash, user.email, user.notes)
        )
        self.db.conn.commit()
        user_id = cursor.lastrowid
        self.audit.log_action(
            AuditAction.CREATE, "user", user_id, changed_by,
            new_value={"username": user.username, "role": user.role.value}
        )
        return user_id

    def get_or_create(self, username: str, changed_by: str = "system") -> User:
        """Get user or auto-create with default settings."""
        user = self.get_by_username(username)
        if user:
            return user
        new_user = User(username=username, display_name=username)
        new_user.id = self.create(new_user, changed_by)
        return new_user

    def _row_to_user(self, row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"] or "",
            role=UserRole(row["role"]),
            discount_percent=row["discount_percent"] or 0.0,
            excluded_from_billing=bool(row["excluded_from_billing"]),
            pin_hash=row["pin_hash"],
            email=row["email"],
            notes=row["notes"],
            active=bool(row["active"]),
        )


class MicroscopeRepository:
    """Repository for Microscope entities (type is immutable)."""

    def __init__(self, db_manager, audit_repo: AuditRepository):
        self.db = db_manager
        self.audit = audit_repo

    def get_all(self, active_only: bool = True) -> List[Microscope]:
        """Get all microscopes."""
        query = "SELECT * FROM microscopes"
        if active_only:
            query += " WHERE active = 1"
        rows = self.db.conn.execute(query).fetchall()
        return [self._row_to_microscope(r) for r in rows]

    def get_by_id(self, microscope_id: int) -> Optional[Microscope]:
        """Get microscope by ID."""
        row = self.db.conn.execute(
            "SELECT * FROM microscopes WHERE id = ?", (microscope_id,)
        ).fetchone()
        return self._row_to_microscope(row) if row else None

    def create(
        self, name: str, serial_number: str,
        microscope_type: MicroscopeType, changed_by: str,
        location: str = ""
    ) -> int:
        """Register new microscope with default billing tiers."""
        cursor = self.db.conn.execute(
            """INSERT INTO microscopes (name, serial_number, microscope_type, location)
               VALUES (?, ?, ?, ?)""",
            (name, serial_number, microscope_type.value, location)
        )
        microscope_id = cursor.lastrowid

        # Create default billing tiers
        default_rate = 225.0 if microscope_type == MicroscopeType.MIRA3_FEG else 150.0
        for tier in BillingTier:
            self.db.conn.execute(
                """INSERT INTO billing_tiers (microscope_id, tier_name, rate_pln_per_hour)
                   VALUES (?, ?, ?)""",
                (microscope_id, tier.value, default_rate)
            )
        self.db.conn.commit()

        self.audit.log_action(
            AuditAction.CREATE, "microscope", microscope_id, changed_by,
            new_value={
                "name": name, "serial_number": serial_number,
                "type": microscope_type.value
            }
        )
        return microscope_id

    def get_tier_rates(self, microscope_id: int) -> List[BillingTierConfig]:
        """Get all billing tier rates for a microscope."""
        rows = self.db.conn.execute(
            "SELECT * FROM billing_tiers WHERE microscope_id = ?",
            (microscope_id,)
        ).fetchall()
        return [
            BillingTierConfig(
                id=r["id"],
                microscope_id=r["microscope_id"],
                tier=BillingTier(r["tier_name"]),
                rate_pln_per_hour=r["rate_pln_per_hour"],
            )
            for r in rows
        ]

    def update_tier_rate(
        self, microscope_id: int, tier: BillingTier,
        rate: float, changed_by: str
    ) -> None:
        """Update billing tier rate for microscope."""
        old_row = self.db.conn.execute(
            """SELECT rate_pln_per_hour FROM billing_tiers
               WHERE microscope_id = ? AND tier_name = ?""",
            (microscope_id, tier.value)
        ).fetchone()
        old_rate = old_row["rate_pln_per_hour"] if old_row else None

        self.db.conn.execute(
            """INSERT OR REPLACE INTO billing_tiers
               (microscope_id, tier_name, rate_pln_per_hour)
               VALUES (?, ?, ?)""",
            (microscope_id, tier.value, rate)
        )
        self.db.conn.commit()
        self.audit.log_action(
            AuditAction.SETTINGS_CHANGE, "billing_tier",
            microscope_id, changed_by,
            {"tier": tier.value, "rate": old_rate},
            {"tier": tier.value, "rate": rate},
        )

    def _row_to_microscope(self, row) -> Microscope:
        return Microscope(
            id=row["id"],
            name=row["name"],
            serial_number=row["serial_number"],
            microscope_type=MicroscopeType(row["microscope_type"]),
            location=row["location"] or "",
            notes=row["notes"],
            active=bool(row["active"]),
        )
