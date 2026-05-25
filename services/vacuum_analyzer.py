"""Vacuum cycle analyzer with state machine and anomaly detection.

Vacuum state machine:
  PUMP -> READY    = OK
  PUMP -> VENT     = ABORTED
  PUMP -> OFF      = ABORTED
  VENT -> OFF      = LEFT_VENTED -> penalty 100 PLN

Anomaly detection:
  LONG_PUMP_TIME   - pumping takes > threshold (default 5 min)
  IDLE_AFTER_READY - long wait READY -> GVL open (default > 30 min)
"""

import logging
from datetime import datetime
from typing import List, Optional

from models.enums import EventType, VacuumStatus, AnomalyType
from models.dataclasses import ParsedEvent, VacuumCycle, Penalty, Anomaly

logger = logging.getLogger(__name__)

# Default thresholds (in seconds)
DEFAULT_PUMP_WARNING_SECONDS = 300    # 5 minutes
DEFAULT_PUMP_CRITICAL_SECONDS = 600   # 10 minutes
DEFAULT_IDLE_THRESHOLD_SECONDS = 1800  # 30 minutes


class VacuumAnalyzer:
    """Analyzes vacuum cycles and detects anomalies."""

    def __init__(
        self,
        pump_warning_seconds: float = DEFAULT_PUMP_WARNING_SECONDS,
        pump_critical_seconds: float = DEFAULT_PUMP_CRITICAL_SECONDS,
        idle_threshold_seconds: float = DEFAULT_IDLE_THRESHOLD_SECONDS,
    ):
        self.pump_warning_seconds = pump_warning_seconds
        self.pump_critical_seconds = pump_critical_seconds
        self.idle_threshold_seconds = idle_threshold_seconds

        self._current_cycle: Optional[VacuumCycle] = None
        self._last_ready_time: Optional[datetime] = None
        self._vented: bool = False

    def analyze_events(
        self,
        events: List[ParsedEvent],
        session_id: Optional[int] = None,
        source_file: str = "",
    ) -> dict:
        """Analyze vacuum-related events and produce cycles, penalties, anomalies.

        Args:
            events: List of parsed events (all types, filtered internally).
            session_id: Optional session ID to associate with cycles.
            source_file: Source file path.

        Returns:
            Dictionary with keys: cycles, penalties, anomalies.
        """
        cycles: List[VacuumCycle] = []
        penalties: List[Penalty] = []
        anomalies: List[Anomaly] = []

        self._current_cycle = None
        self._last_ready_time = None
        self._vented = False

        for event in events:
            result = self._process_event(event, session_id, source_file)
            if result:
                if result.get("cycle"):
                    cycles.append(result["cycle"])
                if result.get("penalty"):
                    penalties.append(result["penalty"])
                if result.get("anomaly"):
                    anomalies.append(result["anomaly"])

        # Check for idle after last ready (if GVL_OPEN comes later)
        # This is handled in _process_gvl_open

        # Finalize unclosed cycle
        if self._current_cycle is not None:
            self._current_cycle.status = VacuumStatus.IN_PROGRESS
            cycles.append(self._current_cycle)
            self._current_cycle = None

        logger.info(
            "Vacuum analysis: %d cycles, %d penalties, %d anomalies",
            len(cycles), len(penalties), len(anomalies),
        )
        return {
            "cycles": cycles,
            "penalties": penalties,
            "anomalies": anomalies,
        }

    def _process_event(
        self,
        event: ParsedEvent,
        session_id: Optional[int],
        source_file: str,
    ) -> Optional[dict]:
        """Process a single event through the vacuum state machine."""
        if event.event_type == EventType.PUMP:
            return self._handle_pump(event, session_id, source_file)
        elif event.event_type == EventType.VAC_READY:
            return self._handle_ready(event, session_id, source_file)
        elif event.event_type == EventType.VENT:
            return self._handle_vent(event, session_id, source_file)
        elif event.event_type == EventType.VAC_OFF:
            return self._handle_off(event, session_id, source_file)
        elif event.event_type == EventType.GVL_OPEN:
            return self._handle_gvl_open(event, session_id, source_file)
        return None

    def _handle_pump(
        self, event: ParsedEvent, session_id: Optional[int], source_file: str
    ) -> Optional[dict]:
        """Handle PUMP command - start of vacuum cycle."""
        result = {}

        # If there was a VENT before this PUMP without OFF, it might
        # just be a new cycle starting
        if self._current_cycle is not None:
            # Previous cycle ends as ABORTED (new pump started)
            self._current_cycle.status = VacuumStatus.ABORTED
            self._current_cycle.end_time = event.timestamp
            result["cycle"] = self._current_cycle

        self._current_cycle = VacuumCycle(
            session_id=session_id,
            pump_start=event.timestamp,
            source_file=source_file,
        )
        self._vented = False
        self._last_ready_time = None

        return result if result else None

    def _handle_ready(
        self, event: ParsedEvent, session_id: Optional[int], source_file: str
    ) -> Optional[dict]:
        """Handle vacuum READY - pumping complete."""
        result = {}

        if self._current_cycle is None:
            # Ready without pump - create a minimal cycle
            self._current_cycle = VacuumCycle(
                session_id=session_id,
                pump_start=event.timestamp,
                source_file=source_file,
            )

        self._current_cycle.ready_time = event.timestamp
        self._last_ready_time = event.timestamp

        # Calculate pump duration and check for LONG_PUMP_TIME
        if self._current_cycle.pump_start:
            delta = event.timestamp - self._current_cycle.pump_start
            pump_seconds = delta.total_seconds()
            self._current_cycle.pump_duration_seconds = pump_seconds

            if pump_seconds > self.pump_warning_seconds:
                severity = "critical" if pump_seconds >= self.pump_critical_seconds else "warning"
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.LONG_PUMP_TIME,
                    session_id=session_id,
                    timestamp=event.timestamp,
                    duration_seconds=pump_seconds,
                    severity=severity,
                    description=(
                        f"Pump time {pump_seconds:.0f}s "
                        f"exceeds threshold {self.pump_warning_seconds:.0f}s"
                    ),
                    source_file=source_file,
                )
                result["anomaly"] = anomaly

        return result if result else None

    def _handle_vent(
        self, event: ParsedEvent, session_id: Optional[int], source_file: str
    ) -> Optional[dict]:
        """Handle VENT command."""
        result = {}
        self._vented = True

        if self._current_cycle is not None:
            # PUMP -> VENT = ABORTED
            self._current_cycle.status = VacuumStatus.ABORTED
            self._current_cycle.end_time = event.timestamp
            if self._current_cycle.pump_start:
                delta = event.timestamp - self._current_cycle.pump_start
                self._current_cycle.pump_duration_seconds = delta.total_seconds()
            result["cycle"] = self._current_cycle
            self._current_cycle = None

        return result if result else None

    def _handle_off(
        self, event: ParsedEvent, session_id: Optional[int], source_file: str
    ) -> Optional[dict]:
        """Handle OFF command."""
        result = {}

        if self._vented:
            # VENT -> OFF = LEFT_VENTED -> penalty
            penalty = Penalty(
                session_id=session_id,
                penalty_type="LEFT_VENTED",
                amount_pln=100.0,
                timestamp=event.timestamp,
                source_file=source_file,
            )
            result["penalty"] = penalty
            self._vented = False
        elif self._current_cycle is not None:
            # PUMP -> OFF = ABORTED
            self._current_cycle.status = VacuumStatus.ABORTED
            self._current_cycle.end_time = event.timestamp
            if self._current_cycle.pump_start:
                delta = event.timestamp - self._current_cycle.pump_start
                self._current_cycle.pump_duration_seconds = delta.total_seconds()
            result["cycle"] = self._current_cycle
            self._current_cycle = None

        return result if result else None

    def _handle_gvl_open(
        self, event: ParsedEvent, session_id: Optional[int], source_file: str
    ) -> Optional[dict]:
        """Handle GVL open - check for IDLE_AFTER_READY anomaly."""
        result = {}

        if self._last_ready_time is not None:
            delta = event.timestamp - self._last_ready_time
            idle_seconds = delta.total_seconds()

            if idle_seconds > self.idle_threshold_seconds:
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.IDLE_AFTER_READY,
                    session_id=session_id,
                    timestamp=event.timestamp,
                    duration_seconds=idle_seconds,
                    severity="warning",
                    description=(
                        f"Idle {idle_seconds:.0f}s after vacuum ready "
                        f"(threshold: {self.idle_threshold_seconds:.0f}s)"
                    ),
                    source_file=source_file,
                )
                result["anomaly"] = anomaly

            self._last_ready_time = None

        # Finalize current cycle as OK (PUMP -> READY -> GVL open)
        if self._current_cycle is not None:
            self._current_cycle.status = VacuumStatus.OK
            self._current_cycle.end_time = event.timestamp
            result["cycle"] = self._current_cycle
            self._current_cycle = None

        return result if result else None
