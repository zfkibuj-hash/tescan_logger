"""Session builder - converts parsed events into Session objects.

Implements business rules:
- VEGA3: work time = HV ON -> HV OFF
- MIRA3 FEG: work time = GVL open -> GVL close
- No manual split (hardware guarantee)
- Cross-month continuity (PARTIAL_SESSION + INCOMPLETE_CONTEXT matching)
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from models.enums import EventType, SessionStatus, MicroscopeType
from models.dataclasses import ParsedEvent, Session

logger = logging.getLogger(__name__)

# Maximum gap between end of one file and start of next for continuity matching
CONTINUITY_GAP_SECONDS = 300  # 5 minutes


class SessionBuilder:
    """Builds Session objects from parsed History log events.

    Business rules:
    - Each HV ON/OFF (VEGA3) or GVL open/close (MIRA3) belongs to exactly one user
    - Sessions cannot span user boundaries (hardware guarantee)
    - Cross-month files are linked via PARTIAL_SESSION + INCOMPLETE_CONTEXT
    """

    def __init__(self, microscope_type: MicroscopeType, microscope_id: int = 0):
        self.microscope_type = microscope_type
        self.microscope_id = microscope_id

    def build_sessions(
        self, events: List[ParsedEvent], source_file: str = ""
    ) -> List[Session]:
        """Build sessions from a list of parsed events.

        Args:
            events: Chronologically sorted ParsedEvent list from one file.
            source_file: Source filename for reference.

        Returns:
            List of Session objects with proper status assignment.
        """
        if not events:
            return []

        if self.microscope_type == MicroscopeType.VEGA3:
            return self._build_vega3_sessions(events, source_file)
        else:
            return self._build_mira3_sessions(events, source_file)

    def _build_vega3_sessions(
        self, events: List[ParsedEvent], source_file: str
    ) -> List[Session]:
        """Build sessions for VEGA3 (HV ON -> HV OFF = work time)."""
        sessions = []
        current_user: Optional[str] = None
        session_start: Optional[datetime] = None
        hv_on: Optional[datetime] = None
        hv_off: Optional[datetime] = None

        # Check if file starts mid-session (INCOMPLETE_CONTEXT)
        first_relevant = self._find_first_relevant_event(events)
        if first_relevant and first_relevant.event_type in (EventType.HV_OFF, EventType.SESSION_END):
            # File starts in the middle of a session
            session = Session(
                microscope_id=self.microscope_id,
                microscope_type=self.microscope_type,
                username="UNKNOWN",
                end_time=first_relevant.timestamp,
                status=SessionStatus.INCOMPLETE_CONTEXT,
                source_file=source_file,
            )
            if first_relevant.event_type == EventType.HV_OFF:
                session.hv_off_time = first_relevant.timestamp
            sessions.append(session)

        for event in events:
            if event.event_type == EventType.SESSION_START:
                current_user = event.username
                session_start = event.timestamp

            elif event.event_type == EventType.HV_ON:
                hv_on = event.timestamp

            elif event.event_type == EventType.HV_OFF:
                if hv_on is not None:
                    hv_off = event.timestamp
                    duration = (hv_off - hv_on).total_seconds()

                    session = Session(
                        microscope_id=self.microscope_id,
                        microscope_type=self.microscope_type,
                        username=current_user or "UNKNOWN",
                        start_time=session_start or hv_on,
                        end_time=hv_off,
                        duration_seconds=duration,
                        status=SessionStatus.COMPLETE,
                        hv_on_time=hv_on,
                        hv_off_time=hv_off,
                        source_file=source_file,
                    )
                    sessions.append(session)
                    hv_on = None
                    hv_off = None

            elif event.event_type == EventType.SESSION_END:
                # If HV was on without OFF, this shouldn't happen (hardware guarantee)
                # but handle gracefully
                if hv_on is not None:
                    logger.warning(
                        "Session ended with HV still ON at %s (should not happen)",
                        event.timestamp
                    )
                session_start = None
                current_user = None

        # Check for PARTIAL_SESSION (HV on at end of file)
        if hv_on is not None:
            session = Session(
                microscope_id=self.microscope_id,
                microscope_type=self.microscope_type,
                username=current_user or "UNKNOWN",
                start_time=session_start or hv_on,
                hv_on_time=hv_on,
                status=SessionStatus.PARTIAL_SESSION,
                source_file=source_file,
            )
            sessions.append(session)

        return sessions

    def _build_mira3_sessions(
        self, events: List[ParsedEvent], source_file: str
    ) -> List[Session]:
        """Build sessions for MIRA3 FEG (GVL open -> GVL close = work time)."""
        sessions = []
        current_user: Optional[str] = None
        session_start: Optional[datetime] = None
        gvl_open: Optional[datetime] = None
        gvl_close: Optional[datetime] = None

        # Check if file starts mid-session (INCOMPLETE_CONTEXT)
        first_relevant = self._find_first_relevant_event_mira3(events)
        if first_relevant and first_relevant.event_type in (EventType.GVL_CLOSE, EventType.SESSION_END):
            session = Session(
                microscope_id=self.microscope_id,
                microscope_type=self.microscope_type,
                username="UNKNOWN",
                end_time=first_relevant.timestamp,
                status=SessionStatus.INCOMPLETE_CONTEXT,
                source_file=source_file,
            )
            if first_relevant.event_type == EventType.GVL_CLOSE:
                session.gvl_close_time = first_relevant.timestamp
            sessions.append(session)

        for event in events:
            if event.event_type == EventType.SESSION_START:
                current_user = event.username
                session_start = event.timestamp

            elif event.event_type == EventType.GVL_OPEN:
                gvl_open = event.timestamp

            elif event.event_type == EventType.GVL_CLOSE:
                if gvl_open is not None:
                    gvl_close = event.timestamp
                    duration = (gvl_close - gvl_open).total_seconds()

                    session = Session(
                        microscope_id=self.microscope_id,
                        microscope_type=self.microscope_type,
                        username=current_user or "UNKNOWN",
                        start_time=session_start or gvl_open,
                        end_time=gvl_close,
                        duration_seconds=duration,
                        status=SessionStatus.COMPLETE,
                        gvl_open_time=gvl_open,
                        gvl_close_time=gvl_close,
                        source_file=source_file,
                    )
                    sessions.append(session)
                    gvl_open = None
                    gvl_close = None

            elif event.event_type == EventType.SESSION_END:
                session_start = None
                current_user = None

        # PARTIAL_SESSION: GVL open at end of file
        if gvl_open is not None:
            session = Session(
                microscope_id=self.microscope_id,
                microscope_type=self.microscope_type,
                username=current_user or "UNKNOWN",
                start_time=session_start or gvl_open,
                gvl_open_time=gvl_open,
                status=SessionStatus.PARTIAL_SESSION,
                source_file=source_file,
            )
            sessions.append(session)

        return sessions

    def _find_first_relevant_event(self, events: List[ParsedEvent]) -> Optional[ParsedEvent]:
        """Find first HV_OFF or SESSION_END before any HV_ON (indicates INCOMPLETE_CONTEXT)."""
        for event in events:
            if event.event_type == EventType.HV_ON:
                return None  # Normal start
            if event.event_type == EventType.SESSION_START:
                return None  # Normal start
            if event.event_type in (EventType.HV_OFF, EventType.SESSION_END):
                return event
        return None

    def _find_first_relevant_event_mira3(self, events: List[ParsedEvent]) -> Optional[ParsedEvent]:
        """Find first GVL_CLOSE or SESSION_END before any GVL_OPEN."""
        for event in events:
            if event.event_type == EventType.GVL_OPEN:
                return None
            if event.event_type == EventType.SESSION_START:
                return None
            if event.event_type in (EventType.GVL_CLOSE, EventType.SESSION_END):
                return event
        return None

    @staticmethod
    def link_cross_month_sessions(
        sessions: List[Session],
    ) -> List[Session]:
        """Link PARTIAL_SESSION from one file with INCOMPLETE_CONTEXT from next.

        Rules:
        - Same username
        - Time gap < CONTINUITY_GAP_SECONDS (5 min)
        - Result: merged into single COMPLETE session

        Args:
            sessions: All sessions from multiple files, sorted by time.

        Returns:
            Sessions with cross-month pairs merged.
        """
        if len(sessions) < 2:
            return sessions

        partial_sessions = [
            (i, s) for i, s in enumerate(sessions)
            if s.status == SessionStatus.PARTIAL_SESSION
        ]
        incomplete_sessions = [
            (i, s) for i, s in enumerate(sessions)
            if s.status == SessionStatus.INCOMPLETE_CONTEXT
        ]

        merged_indices = set()

        for p_idx, partial in partial_sessions:
            for i_idx, incomplete in incomplete_sessions:
                if i_idx in merged_indices:
                    continue

                # Check username match (or UNKNOWN)
                if (partial.username != "UNKNOWN" and
                    incomplete.username != "UNKNOWN" and
                    partial.username != incomplete.username):
                    continue

                # Check time gap
                partial_time = partial.hv_on_time or partial.gvl_open_time or partial.start_time
                incomplete_time = incomplete.hv_off_time or incomplete.gvl_close_time or incomplete.end_time

                if partial_time is None or incomplete_time is None:
                    continue

                gap = abs((incomplete_time - partial_time).total_seconds())
                if gap > CONTINUITY_GAP_SECONDS:
                    continue

                # Merge: partial becomes COMPLETE with end from incomplete
                partial.end_time = incomplete.end_time or incomplete_time
                partial.status = SessionStatus.COMPLETE

                if incomplete.hv_off_time:
                    partial.hv_off_time = incomplete.hv_off_time
                if incomplete.gvl_close_time:
                    partial.gvl_close_time = incomplete.gvl_close_time

                # Recalculate duration
                start = partial.hv_on_time or partial.gvl_open_time or partial.start_time
                end = partial.hv_off_time or partial.gvl_close_time or partial.end_time
                if start and end:
                    partial.duration_seconds = (end - start).total_seconds()

                # Use username from whichever side has it
                if partial.username == "UNKNOWN" and incomplete.username != "UNKNOWN":
                    partial.username = incomplete.username

                merged_indices.add(i_idx)
                merged_indices.add(p_idx)  # Mark partial as processed
                break

        # Return sessions excluding merged INCOMPLETE_CONTEXT entries
        result = [
            s for i, s in enumerate(sessions)
            if i not in merged_indices or sessions[i].status == SessionStatus.COMPLETE
        ]
        # Re-add merged partials (now COMPLETE)
        for p_idx, partial in partial_sessions:
            if p_idx in merged_indices and partial.status == SessionStatus.COMPLETE:
                if partial not in result:
                    result.append(partial)

        result.sort(key=lambda s: s.start_time or datetime.min)
        return result
