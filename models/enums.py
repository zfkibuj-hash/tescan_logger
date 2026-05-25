"""Enumerations for TESCAN Log Analyzer."""

from enum import Enum, auto


class MicroscopeType(Enum):
    """Type of TESCAN microscope - immutable after registration."""
    VEGA3 = "VEGA3"
    MIRA3_FEG = "MIRA3_FEG"


class EventType(Enum):
    """Types of events parsed from History logs."""
    SESSION_START = auto()
    SESSION_END = auto()
    HV_ON = auto()
    HV_OFF = auto()
    FILAMENT_OFF = auto()
    GVL_OPEN = auto()
    GVL_CLOSE = auto()
    VACUUM_PUMP = auto()
    VACUUM_VENT = auto()
    VACUUM_OFF = auto()
    VACUUM_READY = auto()
    SOFTWARE_START = auto()
    SOFTWARE_TERMINATE = auto()


class SessionStatus(Enum):
    """Status of a microscope session."""
    COMPLETE = "COMPLETE"
    PARTIAL_SESSION = "PARTIAL_SESSION"
    INCOMPLETE_CONTEXT = "INCOMPLETE_CONTEXT"
    CANCELLED = "CANCELLED"


class VacuumStatus(Enum):
    """Status of a vacuum cycle."""
    OK = "OK"                    # PUMP -> READY
    ABORTED = "ABORTED"          # PUMP -> VENT or PUMP -> OFF
    LEFT_VENTED = "LEFT_VENTED"  # VENT -> OFF -> penalty 100 PLN
    IN_PROGRESS = "IN_PROGRESS"  # cycle not yet finished


class BillingTier(Enum):
    """Billing tier for a session - determines rate multiplier."""
    PROJECT = "PROJECT"      # Research projects (default)
    UJ_UNIT = "UJ_UNIT"      # Jagiellonian University internal units
    EXTERNAL = "EXTERNAL"    # External entities


class AuditAction(Enum):
    """Actions recorded in audit log."""
    CREATE = "CREATE"
    EDIT = "EDIT"
    CANCEL = "CANCEL"
    OVERRIDE_COST = "OVERRIDE_COST"
    OVERRIDE_TIME = "OVERRIDE_TIME"
    CHANGE_TIER = "CHANGE_TIER"
    CHANGE_RATE = "CHANGE_RATE"
    CHANGE_DISCOUNT = "CHANGE_DISCOUNT"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    BACKUP = "BACKUP"
    SETTINGS_CHANGE = "SETTINGS_CHANGE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    EXCLUDE_INVOICE = "EXCLUDE_INVOICE"


class UserRole(Enum):
    """User roles with different permission levels."""
    ADMIN = "admin"        # Full access + settings + user management
    OPERATOR = "operator"  # Import, edit sessions, PPM operations


class FileType(Enum):
    """Types of log files."""
    HISTORY = "HISTORY"
    HV = "HV"
    UNKNOWN = "UNKNOWN"


class HeatmapType(Enum):
    """Types of heatmaps available."""
    USAGE_TIME = "usage_time"
    PUMPING_TIME = "pumping_time"
    PENALTIES = "penalties"
    VACUUM_ANOMALIES = "vacuum_anomalies"
    IDLE_TIME = "idle_time"
    GVL_OPEN_TIME = "gvl_open_time"


class HeatmapGranularity(Enum):
    """Time granularity for heatmaps."""
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class AnomalyType(Enum):
    """Types of detected anomalies."""
    PRESSURE_SPIKE = "pressure_spike"
    EMISSION_DRIFT = "emission_drift"
    VACUUM_DEGRADATION = "vacuum_degradation"
    HV_INSTABILITY = "hv_instability"
    LONG_PUMP_TIME = "long_pump_time"
    IDLE_AFTER_READY = "idle_after_ready"
    HV_LOG_GAP = "hv_log_gap"
