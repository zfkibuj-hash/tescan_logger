"""Vacuum cycle analyzer - processes vacuum events into cycles with penalties.

Business rules:
- PUMP -> READY = OK
- PUMP -> VENT = ABORTED
- PUMP -> OFF = ABORTED
- VENT -> OFF = LEFT_VENTED -> penalty 100 PLN

Anomaly detection:
- LONG_PUMP_TIME: ready_time exceeds threshold (possible contamination / outgassing)
- IDLE_AFTER_READY: long gap between READY and HV ON/GVL open (microscope unused)
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from models.enums import EventType, VacuumStatus, AnomalyType
from models.dataclasses import ParsedEvent, VacuumCycle, Penalty, Anomaly

logger = logging.getLogger(__name__)

PENALTY_AMOUNT = 100.0  # PLN

# Anomaly thresholds (configurable later via settings)
LONG_PUMP_THRESHOLD_SECONDS = 300.0  # >5 min pump time = suspicious
IDLE_AFTER_READY_THRESHOLD_SECONDS = 1800.0  # >30 min idle after ready = flagged


class VacuumAnalyzer:
    """Analyzes vacuum events and builds VacuumCycle + Penalty objects.

    Tracks state machine:
    - PUMP starts a cycle
    - READY completes it successfully (OK)
    - VENT or OFF during pumping = ABORTED
    - VENT followed by OFF = LEFT_VENTED (penalty)
    """

    def __init__(self, microscope_id: int = 0,
                 long_pump_threshold: float = LONG_PUMP_THRESHOLD_SECONDS,
                 idle_threshold: float = IDLE_AFTER_READY_THRESHOLD_SECONDS):
        self.microscope_id = microscope_id
        self.long_pump_threshold = long_pump_threshold
        self.idle_threshold = idle_threshold

    def analyze(
        self, events: List[ParsedEvent], source_file: str = ""
    ) -> Tuple[List[VacuumCycle], List[Penalty], List[Anomaly]]:
        """Analyze vacuum events and produce cycles + penalties + anomalies.

        Args:
            events: All parsed events (filtered to vacuum-related internally).
            source_file: Source file for reference.

        Returns:
            Tuple of (vacuum_cycles, penalties, anomalies).
        """
        cycles: List[VacuumCycle] = []
        penalties: List[Penalty] = []
        anomalies: List[Anomaly] = []

        current_user: Optional[str] = None
        current_session_id: Optional[int] = None

        # State tracking
        pump_start: Optional[datetime] = None
        vent_start: Optional[datetime] = None
        vacuum_ready_time: Optional[datetime] = None  # When READY was achieved
        is_pumping: bool = False
        is_venting: bool = False

        for event in events:
            # Track current user
            if event.event_type == EventType.SESSION_START:
                current_user = event.username
            elif event.event_type == EventType.SESSION_END:
                current_user = None

            # ANOMALY: Idle after ready - user started measurement long after vacuum ready
            elif event.event_type in (EventType.HV_ON, EventType.GVL_OPEN):
                if vacuum_ready_time is not None:
                    idle_gap = (event.timestamp - vacuum_ready_time).total_seconds()
                    if idle_gap > self.idle_threshold:
                        anomalies.append(Anomaly(
                            microscope_id=self.microscope_id,
                            session_id=current_session_id,
                            anomaly_type=AnomalyType.IDLE_AFTER_READY,
                            severity="info" if idle_gap < 7200 else "warning",
                            timestamp=event.timestamp,
                            description=(
                                f"Long idle after vacuum ready: {idle_gap/60:.0f} min "
                                f"(ready at {vacuum_ready_time.strftime('%H:%M')}, "
                                f"measurement started at {event.timestamp.strftime('%H:%M')}). "
                                f"User: {current_user}."
                            ),
                            value=idle_gap,
                            threshold=self.idle_threshold,
                            source_file=source_file,
                        ))
                        logger.info(
                            "IDLE_AFTER_READY: %.0f min for user=%s at %s",
                            idle_gap / 60, current_user, event.timestamp
                        )
                vacuum_ready_time = None  # Reset after measurement starts

            # Vacuum state machine
            elif event.event_type == EventType.VACUUM_PUMP:
                # Start new pump cycle
                pump_start = event.timestamp
                is_pumping = True
                is_venting = False

            elif event.event_type == EventType.VACUUM_READY:
                # PUMP -> READY = OK
                if is_pumping and pump_start is not None:
                    ready_seconds = None
                    if event.details:
                        try:
                            ready_seconds = float(event.details)
                        except ValueError:
                            pass

                    duration = (event.timestamp - pump_start).total_seconds()
                    cycle = VacuumCycle(
                        microscope_id=self.microscope_id,
                        session_id=current_session_id,
                        username=current_user,
                        command="PUMP",
                        start_time=pump_start,
                        end_time=event.timestamp,
                        duration_seconds=duration,
                        status=VacuumStatus.OK,
                        ready_time_seconds=ready_seconds,
                        source_file=source_file,
                    )
                    cycles.append(cycle)

                    # ANOMALY: Long pump time (possible contamination/outgassing)
                    effective_ready = ready_seconds if ready_seconds else duration
                    if effective_ready > self.long_pump_threshold:
                        anomalies.append(Anomaly(
                            microscope_id=self.microscope_id,
                            session_id=current_session_id,
                            anomaly_type=AnomalyType.LONG_PUMP_TIME,
                            severity="warning" if effective_ready < 600 else "critical",
                            timestamp=event.timestamp,
                            description=(
                                f"Long pump time: {effective_ready:.0f}s "
                                f"(threshold: {self.long_pump_threshold:.0f}s). "
                                f"User: {current_user}. "
                                f"Possible sample contamination or outgassing."
                            ),
                            value=effective_ready,
                            threshold=self.long_pump_threshold,
                            source_file=source_file,
                        ))
                        logger.warning(
                            "LONG_PUMP_TIME: %.0fs for user=%s at %s",
                            effective_ready, current_user, event.timestamp
                        )

                is_pumping = False
                pump_start = None
                vacuum_ready_time = event.timestamp  # Track when vacuum became ready

            elif event.event_type == EventType.VACUUM_VENT:
                if is_pumping and pump_start is not None:
                    # PUMP -> VENT = ABORTED
                    duration = (event.timestamp - pump_start).total_seconds()
                    cycle = VacuumCycle(
                        microscope_id=self.microscope_id,
                        session_id=current_session_id,
                        username=current_user,
                        command="PUMP",
                        start_time=pump_start,
                        end_time=event.timestamp,
                        duration_seconds=duration,
                        status=VacuumStatus.ABORTED,
                        source_file=source_file,
                    )
                    cycles.append(cycle)
                    is_pumping = False
                    pump_start = None

                # Start VENT tracking
                vent_start = event.timestamp
                is_venting = True

            elif event.event_type == EventType.VACUUM_OFF:
                if is_pumping and pump_start is not None:
                    # PUMP -> OFF = ABORTED
                    duration = (event.timestamp - pump_start).total_seconds()
                    cycle = VacuumCycle(
                        microscope_id=self.microscope_id,
                        session_id=current_session_id,
                        username=current_user,
                        command="PUMP",
                        start_time=pump_start,
                        end_time=event.timestamp,
                        duration_seconds=duration,
                        status=VacuumStatus.ABORTED,
                        source_file=source_file,
                    )
                    cycles.append(cycle)
                    is_pumping = False
                    pump_start = None

                elif is_venting and vent_start is not None:
                    # VENT -> OFF = LEFT_VENTED -> penalty!
                    duration = (event.timestamp - vent_start).total_seconds()
                    cycle = VacuumCycle(
                        microscope_id=self.microscope_id,
                        session_id=current_session_id,
                        username=current_user,
                        command="VENT",
                        start_time=vent_start,
                        end_time=event.timestamp,
                        duration_seconds=duration,
                        status=VacuumStatus.LEFT_VENTED,
                        source_file=source_file,
                    )
                    cycles.append(cycle)

                    # Create penalty
                    penalty = Penalty(
                        microscope_id=self.microscope_id,
                        username=current_user or "UNKNOWN",
                        amount=PENALTY_AMOUNT,
                        reason="LEFT_VENTED",
                        timestamp=event.timestamp,
                    )
                    penalties.append(penalty)
                    logger.warning(
                        "LEFT_VENTED penalty: user=%s at %s",
                        current_user, event.timestamp
                    )

                is_venting = False
                vent_start = None

        logger.info(
            "Vacuum analysis: %d cycles, %d penalties, %d anomalies from %s",
            len(cycles), len(penalties), len(anomalies), source_file
        )
        return cycles, penalties, anomalies
