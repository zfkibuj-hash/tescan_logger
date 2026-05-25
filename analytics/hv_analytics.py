"""HV analytics — emission drift, pressure spikes, diagnostics.

Analyzes HV sample data to detect anomalies and generate statistics.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from models.hv_models import HVSample, HVSessionStats, PressureEvent
from models.enums import AnomalyType, MicroscopeType
from models.dataclasses import Anomaly

logger = logging.getLogger(__name__)

# Thresholds
PRESSURE_SPIKE_FACTOR = 10.0  # 10x above baseline = spike
EMISSION_DRIFT_THRESHOLD = 20.0  # 20% drift = anomaly
HV_INSTABILITY_THRESHOLD = 5.0  # 5% deviation from set value
HV_LOG_GAP_SECONDS = 3600  # 1 hour gap = warning


class HVAnalytics:
    """Analyzes HV sample data for anomalies and statistics."""

    def compute_session_stats(
        self, samples: List[HVSample],
        microscope_type: MicroscopeType = MicroscopeType.VEGA3
    ) -> HVSessionStats:
        """Compute aggregated statistics from HV samples."""
        if not samples:
            return HVSessionStats()

        stats = HVSessionStats(
            microscope_type=microscope_type,
            start_time=samples[0].timestamp,
            end_time=samples[-1].timestamp,
            sample_count=len(samples),
        )

        hv_values = [s.actual_hv_kv for s in samples if s.actual_hv_kv > 0]
        emission_values = [s.emission_current_ua for s in samples]
        filament_values = [s.filament_current_a for s in samples]
        chamber_values = [s.chamber_pressure_pa for s in samples]
        gun_values = [s.gun_pressure_pa for s in samples]

        if hv_values:
            stats.avg_hv_kv = sum(hv_values) / len(hv_values)
            stats.max_hv_kv = max(hv_values)
            set_values = [s.set_hv_kv for s in samples if s.set_hv_kv > 0]
            if set_values:
                avg_set = sum(set_values) / len(set_values)
                if avg_set > 0:
                    deviations = [
                        abs(s.actual_hv_kv - s.set_hv_kv) / s.set_hv_kv * 100
                        for s in samples if s.set_hv_kv > 0
                    ]
                    stats.hv_stability_percent = (
                        sum(deviations) / len(deviations) if deviations else 0
                    )

        if emission_values:
            stats.avg_emission_ua = sum(emission_values) / len(emission_values)
            stats.max_emission_ua = max(emission_values)
            stats.min_emission_ua = min(emission_values)
            if stats.avg_emission_ua > 0:
                stats.emission_drift_percent = (
                    (stats.max_emission_ua - stats.min_emission_ua)
                    / stats.avg_emission_ua * 100
                )

        if filament_values:
            stats.avg_filament_current_a = sum(filament_values) / len(filament_values)
            stats.max_filament_current_a = max(filament_values)

        if chamber_values:
            stats.avg_chamber_pressure_pa = sum(chamber_values) / len(chamber_values)
            stats.max_chamber_pressure_pa = max(chamber_values)

        if gun_values:
            stats.avg_gun_pressure_pa = sum(gun_values) / len(gun_values)
            stats.max_gun_pressure_pa = max(gun_values)

        return stats


    def detect_pressure_spikes(
        self, samples: List[HVSample], microscope_id: int = 0
    ) -> List[PressureEvent]:
        """Detect pressure spikes in HV sample data.

        A spike is defined as pressure > PRESSURE_SPIKE_FACTOR × baseline.
        Baseline = rolling median of last 60 samples.
        """
        if len(samples) < 60:
            return []

        events = []
        window_size = 60

        for i in range(window_size, len(samples)):
            window = samples[i - window_size:i]

            # Chamber pressure baseline
            chamber_baseline = sorted(
                [s.chamber_pressure_pa for s in window]
            )[window_size // 2]

            current = samples[i]

            if (chamber_baseline > 0 and
                current.chamber_pressure_pa > chamber_baseline * PRESSURE_SPIKE_FACTOR):
                events.append(PressureEvent(
                    microscope_id=microscope_id,
                    timestamp=current.timestamp,
                    pressure_type="chamber",
                    pressure_value_pa=current.chamber_pressure_pa,
                    baseline_pa=chamber_baseline,
                    spike_factor=current.chamber_pressure_pa / chamber_baseline,
                    source_file=current.source_file,
                ))

            # Gun pressure baseline
            gun_baseline = sorted(
                [s.gun_pressure_pa for s in window]
            )[window_size // 2]

            if (gun_baseline > 0 and
                current.gun_pressure_pa > gun_baseline * PRESSURE_SPIKE_FACTOR):
                events.append(PressureEvent(
                    microscope_id=microscope_id,
                    timestamp=current.timestamp,
                    pressure_type="gun",
                    pressure_value_pa=current.gun_pressure_pa,
                    baseline_pa=gun_baseline,
                    spike_factor=current.gun_pressure_pa / gun_baseline,
                    source_file=current.source_file,
                ))

        return events

    def detect_log_gaps(
        self, samples: List[HVSample], microscope_id: int = 0
    ) -> List[Anomaly]:
        """Detect gaps > 1 hour in HV log (possible data loss)."""
        anomalies = []

        for i in range(1, len(samples)):
            if samples[i].timestamp and samples[i-1].timestamp:
                gap = (samples[i].timestamp - samples[i-1].timestamp).total_seconds()
                if gap > HV_LOG_GAP_SECONDS:
                    anomalies.append(Anomaly(
                        microscope_id=microscope_id,
                        anomaly_type=AnomalyType.HV_LOG_GAP,
                        severity="warning",
                        timestamp=samples[i-1].timestamp,
                        description=f"HV log gap: {gap/3600:.1f} hours",
                        value=gap,
                        threshold=float(HV_LOG_GAP_SECONDS),
                        source_file=samples[i].source_file,
                    ))

        return anomalies

    def detect_emission_drift(
        self, samples: List[HVSample], microscope_id: int = 0
    ) -> List[Anomaly]:
        """Detect significant emission current drift within a session."""
        if len(samples) < 100:
            return []

        anomalies = []
        # Compare first 10% vs last 10%
        n = len(samples)
        first_chunk = samples[:n // 10]
        last_chunk = samples[-n // 10:]

        avg_first = sum(s.emission_current_ua for s in first_chunk) / len(first_chunk)
        avg_last = sum(s.emission_current_ua for s in last_chunk) / len(last_chunk)

        if avg_first > 0:
            drift_percent = abs(avg_last - avg_first) / avg_first * 100
            if drift_percent > EMISSION_DRIFT_THRESHOLD:
                anomalies.append(Anomaly(
                    microscope_id=microscope_id,
                    anomaly_type=AnomalyType.EMISSION_DRIFT,
                    severity="warning" if drift_percent < 50 else "critical",
                    timestamp=samples[-1].timestamp,
                    description=f"Emission drift: {drift_percent:.1f}% ({avg_first:.2f} → {avg_last:.2f} µA)",
                    value=drift_percent,
                    threshold=EMISSION_DRIFT_THRESHOLD,
                    source_file=samples[0].source_file,
                ))

        return anomalies
