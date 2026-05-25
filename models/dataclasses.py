"""Data classes for TESCAN Log Analyzer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models.enums import (
    EventType, SessionStatus, VacuumStatus, MicroscopeType,
    AuditAction, UserRole, AnomalyType, BillingTier
)


@dataclass
class ParsedEvent:
    """Single event parsed from a History log line."""
    timestamp: datetime
    event_type: EventType
    raw_line: str
    username: Optional[str] = None
    details: Optional[str] = None
    line_number: int = 0
    source_file: str = ""


@dataclass
class Session:
    """Microscope usage session."""
    id: Optional[int] = None
    microscope_id: int = 0
    microscope_type: MicroscopeType = MicroscopeType.VEGA3
    username: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: SessionStatus = SessionStatus.COMPLETE
    # Billing
    billing_tier: BillingTier = BillingTier.PROJECT
    hourly_rate: float = 150.0
    rate_override: Optional[float] = None
    discount_percent: float = 0.0
    calculated_cost: float = 0.0
    cost_override: Optional[float] = None
    time_override_minutes: Optional[float] = None
    excluded_from_invoice: bool = False
    cancelled: bool = False
    # HV/GVL markers
    hv_on_time: Optional[datetime] = None
    hv_off_time: Optional[datetime] = None
    gvl_open_time: Optional[datetime] = None
    gvl_close_time: Optional[datetime] = None
    # Metadata
    notes: Optional[str] = None
    source_file: str = ""
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def effective_rate(self) -> float:
        """Effective hourly rate (override or default)."""
        if self.rate_override is not None:
            return self.rate_override
        return self.hourly_rate

    @property
    def effective_duration_seconds(self) -> float:
        """Duration after applying time override."""
        if self.time_override_minutes is not None:
            return self.time_override_minutes * 60.0
        return self.duration_seconds

    @property
    def effective_cost(self) -> float:
        """Final cost after all overrides and discounts."""
        if self.cancelled:
            return 0.0
        if self.cost_override is not None:
            return self.cost_override
        # Discount reduces TIME, not rate
        effective_hours = self.effective_duration_seconds / 3600.0
        discount_factor = 1.0 - (self.discount_percent / 100.0)
        billable_hours = effective_hours * discount_factor
        return round(billable_hours * self.effective_rate, 2)

    @property
    def duration_minutes(self) -> float:
        """Duration in minutes."""
        return self.effective_duration_seconds / 60.0


@dataclass
class VacuumCycle:
    """A vacuum pump/vent cycle with status tracking."""
    id: Optional[int] = None
    microscope_id: int = 0
    session_id: Optional[int] = None
    username: Optional[str] = None
    command: str = ""  # PUMP, VENT, OFF
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: VacuumStatus = VacuumStatus.IN_PROGRESS
    ready_time_seconds: Optional[float] = None
    source_file: str = ""
    created_at: Optional[datetime] = None


@dataclass
class User:
    """Microscope operator/user."""
    id: Optional[int] = None
    username: str = ""
    display_name: str = ""
    role: UserRole = UserRole.OPERATOR
    discount_percent: float = 0.0
    excluded_from_billing: bool = False
    pin_hash: Optional[str] = None  # For GLP operator confirmation
    email: Optional[str] = None
    notes: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Microscope:
    """Registered microscope - type is immutable after creation."""
    id: Optional[int] = None
    name: str = ""
    serial_number: str = ""
    microscope_type: MicroscopeType = MicroscopeType.VEGA3  # IMMUTABLE
    location: str = ""
    notes: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None

    @property
    def default_rate(self) -> float:
        """Default hourly rate based on microscope type."""
        if self.microscope_type == MicroscopeType.MIRA3_FEG:
            return 225.0
        return 150.0


@dataclass
class BillingTierConfig:
    """Billing tier rate configuration per microscope."""
    id: Optional[int] = None
    microscope_id: int = 0
    tier: BillingTier = BillingTier.PROJECT
    rate_pln_per_hour: float = 150.0


@dataclass
class Anomaly:
    """Detected anomaly during log analysis."""
    id: Optional[int] = None
    microscope_id: int = 0
    session_id: Optional[int] = None
    anomaly_type: AnomalyType = AnomalyType.PRESSURE_SPIKE
    severity: str = "warning"  # info, warning, critical
    timestamp: Optional[datetime] = None
    description: str = ""
    value: Optional[float] = None
    threshold: Optional[float] = None
    source_file: str = ""
    resolved: bool = False
    created_at: Optional[datetime] = None


@dataclass
class Penalty:
    """Penalty for LEFT_VENTED vacuum cycle - always 100 PLN."""
    id: Optional[int] = None
    vacuum_cycle_id: int = 0
    microscope_id: int = 0
    username: str = ""
    amount: float = 100.0
    reason: str = "LEFT_VENTED"
    timestamp: Optional[datetime] = None
    paid: bool = False
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class AuditEntry:
    """Audit log entry - GLP compliant, UTC timestamps."""
    id: Optional[int] = None
    action: AuditAction = AuditAction.EDIT
    entity_type: str = ""  # 'session', 'user', 'vacuum_cycle', etc.
    entity_id: Optional[int] = None
    changed_by: str = ""  # current operator username
    old_value: Optional[str] = None  # JSON
    new_value: Optional[str] = None  # JSON
    description: Optional[str] = None
    created_at: Optional[datetime] = None  # UTC
