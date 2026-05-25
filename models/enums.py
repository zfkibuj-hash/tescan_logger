"""Enumerations for TESCAN VEGA3 Log Analyzer."""

from enum import Enum


class EventType(Enum):
    """Types of events parsed from history logs."""

    SESSION_START = "SESSION_START"
    SESSION_FINISH = "SESSION_FINISH"
    HV_ON = "HV_ON"
    HV_OFF = "HV_OFF"
    HV_HEATING_OFF = "HV_HEATING_OFF"
    HV_TURNING_ON = "HV_TURNING_ON"
    HV_TURNING_OFF = "HV_TURNING_OFF"
    GVL_OPEN = "GVL_OPEN"
    GVL_CLOSE = "GVL_CLOSE"
    PUMP = "PUMP"
    VENT = "VENT"
    VAC_OFF = "VAC_OFF"
    VAC_READY = "VAC_READY"
    SOFTWARE_START = "SOFTWARE_START"
    SOFTWARE_TERMINATE = "SOFTWARE_TERMINATE"
    SERIAL_NUMBER = "SERIAL_NUMBER"
    FILAMENT_TIME = "FILAMENT_TIME"
    VACUUM_TIME = "VACUUM_TIME"
    CHAMBER_VIEW = "CHAMBER_VIEW"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class SessionStatus(Enum):
    """Status of a user session."""

    COMPLETE = "COMPLETE"
    NO_MEASUREMENT = "NO_MEASUREMENT"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class VacuumStatus(Enum):
    """Status of a vacuum pump cycle."""

    OK = "OK"
    ABORTED = "ABORTED"
    LEFT_VENTED = "LEFT_VENTED"
    IN_PROGRESS = "IN_PROGRESS"


class AnomalyType(Enum):
    """Types of detected anomalies."""

    LONG_PUMP_TIME = "LONG_PUMP_TIME"
    IDLE_AFTER_READY = "IDLE_AFTER_READY"


class AuditAction(Enum):
    """Types of audit log actions."""

    IMPORT = "IMPORT"
    DELETE_FILE = "DELETE_FILE"
    EDIT = "EDIT"
    CANCEL = "CANCEL"
    OVERRIDE_COST = "OVERRIDE_COST"
    OVERRIDE_TIME = "OVERRIDE_TIME"
    CHANGE_DISCOUNT = "CHANGE_DISCOUNT"
    EXCLUDE_BILLING = "EXCLUDE_BILLING"
    CHANGE_SETTING = "CHANGE_SETTING"
    ADD_USER = "ADD_USER"
    EDIT_USER = "EDIT_USER"
    DELETE_USER = "DELETE_USER"


class FileType(Enum):
    """Types of log files."""

    HISTORY = "HISTORY"
    HV = "HV"
