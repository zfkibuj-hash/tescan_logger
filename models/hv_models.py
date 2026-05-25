"""HV/Emission log data models for TESCAN Log Analyzer."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from models.enums import MicroscopeType


@dataclass
class HVSample:
    """Single HV/emission measurement sample (1 per second in log)."""
    id: Optional[int] = None
    microscope_id: int = 0
    timestamp: Optional[datetime] = None
    source_file: str = ""
    # Common fields
    set_hv_kv: float = 0.0
    actual_hv_kv: float = 0.0
    emission_current_ua: float = 0.0
    filament_current_a: float = 0.0
    gun_pressure_pa: float = 0.0
    chamber_pressure_pa: float = 0.0
    # VEGA3 specific
    heating_percent: Optional[float] = None
    gun_valve_state: Optional[str] = None  # "Open" / "Closed"
    # MIRA3 FEG specific
    extractor_voltage_kv: Optional[float] = None
    suppressor_voltage_v: Optional[float] = None
    total_current_ua: Optional[float] = None
    flags_hex: Optional[str] = None
    column_ion_pump_pressure_pa: Optional[float] = None

    @property
    def is_hv_active(self) -> bool:
        """Check if HV is actively on (non-zero)."""
        return self.actual_hv_kv > 0.0

    @property
    def is_gvl_open(self) -> bool:
        """Check if Gun Valve is open (VEGA3 HV log only)."""
        return self.gun_valve_state == "Open"


@dataclass
class HVSessionStats:
    """Aggregated statistics from HV data for a session."""
    session_id: Optional[int] = None
    microscope_id: int = 0
    microscope_type: MicroscopeType = MicroscopeType.VEGA3
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    sample_count: int = 0
    # HV stats
    avg_hv_kv: float = 0.0
    max_hv_kv: float = 0.0
    hv_stability_percent: float = 0.0
    # Emission stats
    avg_emission_ua: float = 0.0
    max_emission_ua: float = 0.0
    min_emission_ua: float = 0.0
    emission_drift_percent: float = 0.0
    # Pressure stats
    avg_chamber_pressure_pa: float = 0.0
    max_chamber_pressure_pa: float = 0.0
    avg_gun_pressure_pa: float = 0.0
    max_gun_pressure_pa: float = 0.0
    pressure_spike_count: int = 0
    # Filament stats
    avg_filament_current_a: float = 0.0
    max_filament_current_a: float = 0.0


@dataclass
class PressureEvent:
    """Detected pressure spike or anomaly from HV data."""
    id: Optional[int] = None
    microscope_id: int = 0
    session_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    pressure_type: str = "chamber"  # "chamber" or "gun"
    pressure_value_pa: float = 0.0
    baseline_pa: float = 0.0
    spike_factor: float = 0.0  # how many times above baseline
    duration_seconds: float = 0.0
    source_file: str = ""
    created_at: Optional[datetime] = None
