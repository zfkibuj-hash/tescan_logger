"""Vacuum cycle analyzer — processes vacuum events into cycles with penalties.

Business rules:
- PUMP → READY = OK
- PUMP → VENT = ABORTED
- PUMP → OFF = ABORTED
- VENT → OFF = LEFT_VENTED → penalty 100 PLN
"""

import logging
from datetime import datetime
from typing import List, Optional

from models.enums import EventType, VacuumStatus
from models.dataclasses import ParsedEvent, VacuumCycle, Penalty

logger = logging.getLogger(__name__)

PENALTY_AMOUNT = 100.0  # PLN


class VacuumAnalyzer:
    """Analyzes vacuum events and builds VacuumCycle + Penalty objects.

    Tracks state machine:
    - PUMP starts a cycle
    - READY completes it successfully (OK)
    - VENT or OFF during pumping = ABORTED
    - VENT followed by OFF = LEFT_VENTED (penalty)
    """

    def __init__(self, microscope_id: int = 0):
        self.microscope_id = microscope_id

    def analyze(
        self, events: List[ParsedEvent], source_file: str = ""
    ) -> tuple[List[VacuumCycle], List[Penalty]]:
        """Analyze vacuum events and produce cycles + penalties.

        Args:
            events: All parsed events (filtered to vacuum-related internally).
            source_file: Source file for reference.

        Returns:
            Tuple of (vacuum_cycles, penalties).
        """
        cycles: List[VacuumCycle] = []
        penalties: List[Penalty] = []

        current_user: Optional[str] = None
        current_session_id: Optional[int] = None

        # State tracking
        pump_start: Optional[datetime] = None
        vent_start: Optional[datetime] = None
        is_pumping: bool = False
        is_venting: bool = False

        for event in events:
            # Track current user
            if event.event_type == EventType.SESSION_START:
                current_user = event.username
            elif event.event_type == EventType.SESSION_END:
                current_user = None

            # Vacuum state machine
            elif event.event_type == EventType.VACUUM_PUMP:
                # Start new pump cycle
                pump_start = event.timestamp
                is_pumping = True
                is_venting = False

            elif event.event_type == EventType.VACUUM_READY:
                # PUMP → READY = OK
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

                is_pumping = False
                pump_start = None

            elif event.event_type == EventType.VACUUM_VENT:
                if is_pumping and pump_start is not None:
                    # PUMP → VENT = ABORTED
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
                    # PUMP → OFF = ABORTED
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
                    # VENT → OFF = LEFT_VENTED → penalty!
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
            "Vacuum analysis: %d cycles, %d penalties from %s",
            len(cycles), len(penalties), source_file
        )
        return cycles, penalties
