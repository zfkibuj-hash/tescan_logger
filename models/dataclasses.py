"""Data classes for TESCAN VEGA3 Log Analyzer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models.enums import (
    EventType,
    SessionStatus,
    VacuumStatus,
    AnomalyType,
    AuditAction,
    FileType,
)


@dataclass
class ParsedEvent:
    """A single parsed event from the history log."""

    timestamp: datetime
    event_type: EventType
    raw_line: str
    details: Optional[str] = None
    source_file: Optional[str] = None
    line_number: int = 0


@dataclass
class GVLCycle:
    """A single GVL open->close cycle within a session."""

    open_time: datetime
    close_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds of this GVL cycle."""
        if self.close_time is None:
            return 0.0
        delta = self.close_time - self.open_time
        return delta.total_seconds()


@dataclass
class Session:
    """A user session on the microscope."""

    id: Optional[int] = None
    username: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    gvl_total_seconds: float = 0.0
    gvl_cycles: list = field(default_factory=list)
    status: SessionStatus = SessionStatus.COMPLETE
    cost: float = 0.0
    discount_percent: float = 0.0
    discount_hours: float = 0.0  # hours subtracted from billable time (e.g. -2h)
    override_cost: Optional[float] = None
    override_time_minutes: Optional[float] = None
    excluded_from_billing: bool = False
    source_file: str = ""
    notes: str = ""

    @property
    def billable_seconds(self) -> float:
        """Effective billable time after all discounts.

        Priority:
        1. override_time_minutes set -> use that directly
        2. Otherwise: gvl_total * (1 - discount%) - discount_hours*3600
        """
        if self.override_time_minutes is not None:
            return self.override_time_minutes * 60.0
        effective = self.gvl_total_seconds * (1.0 - self.discount_percent / 100.0)
        effective -= self.discount_hours * 3600.0
        return max(effective, 0.0)


@dataclass
class VacuumCycle:
    """A vacuum pump cycle (PUMP -> READY/VENT/OFF)."""

    id: Optional[int] = None
    session_id: Optional[int] = None
    pump_start: Optional[datetime] = None
    ready_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: VacuumStatus = VacuumStatus.IN_PROGRESS
    pump_duration_seconds: float = 0.0
    source_file: str = ""


@dataclass
class HVSample:
    """A single HV data sample (1 per second)."""

    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    set_hv_kv: float = 0.0
    actual_hv_kv: float = 0.0
    emission_current_ua: float = 0.0
    emitter_current_a: float = 0.0
    heating_percent: float = 0.0
    gun_pressure_pa: float = 0.0
    chamber_pressure_pa: float = 0.0
    gun_valve_state: str = "Closed"
    source_file: str = ""


@dataclass
class User:
    """A microscope user."""

    id: Optional[int] = None
    username: str = ""
    display_name: str = ""
    discount_percent: float = 0.0
    excluded_from_billing: bool = False
    pin_hash: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Penalty:
    """A penalty record (e.g. LEFT_VENTED)."""

    id: Optional[int] = None
    session_id: Optional[int] = None
    vacuum_cycle_id: Optional[int] = None
    penalty_type: str = "LEFT_VENTED"
    amount_pln: float = 100.0
    username: str = ""
    timestamp: Optional[datetime] = None
    source_file: str = ""
    notes: str = ""


@dataclass
class Anomaly:
    """A detected anomaly."""

    id: Optional[int] = None
    anomaly_type: AnomalyType = AnomalyType.LONG_PUMP_TIME
    session_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    duration_seconds: float = 0.0
    severity: str = "warning"
    description: str = ""
    source_file: str = ""


@dataclass
class AuditEntry:
    """An audit log entry."""

    id: Optional[int] = None
    action: AuditAction = AuditAction.EDIT
    entity_type: str = ""
    entity_id: Optional[int] = None
    changed_by: str = "system"
    old_value: str = ""
    new_value: str = ""
    created_at: Optional[datetime] = None


@dataclass
class FileRecord:
    """Record of an imported file."""

    id: Optional[int] = None
    file_path: str = ""
    file_hash: str = ""
    file_type: FileType = FileType.HISTORY
    import_date: Optional[datetime] = None
    record_count: int = 0
