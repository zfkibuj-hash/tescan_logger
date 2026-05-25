"""Session builder - converts parsed events into sessions.

CRITICAL RULES:
- GVL open -> GVL close = billable time (NOT HV ON/OFF!)
- Multiple GVL cycles per session are SUMMED
- Session without any GVL open = NO_MEASUREMENT status
- Session without session_finished = PARTIAL status
"""

import logging
from datetime import datetime
from typing import List, Optional

from models.enums import EventType, SessionStatus
from models.dataclasses import ParsedEvent, Session, GVLCycle

logger = logging.getLogger(__name__)


class SessionBuilder:
    """Builds sessions from a list of parsed events."""

    def __init__(self):
        self._current_session: Optional[Session] = None
        self._current_gvl_open: Optional[datetime] = None
        self._sessions: List[Session] = []

    def build_sessions(
        self, events: List[ParsedEvent], source_file: str = ""
    ) -> List[Session]:
        """Build sessions from a list of parsed events.

        Args:
            events: List of parsed events sorted by timestamp.
            source_file: Source file path for tracking.

        Returns:
            List of built sessions.
        """
        self._sessions = []
        self._current_session = None
        self._current_gvl_open = None

        for event in events:
            self._process_event(event, source_file)

        # Handle unclosed session at end of file
        if self._current_session is not None:
            self._finalize_partial_session(source_file)

        logger.info(
            "Built %d sessions from %s",
            len(self._sessions), source_file,
        )
        return self._sessions

    def _process_event(self, event: ParsedEvent, source_file: str) -> None:
        """Process a single event in the context of session building."""
        if event.event_type == EventType.SESSION_START:
            self._handle_session_start(event, source_file)
        elif event.event_type == EventType.SESSION_FINISH:
            self._handle_session_finish(event, source_file)
        elif event.event_type == EventType.GVL_OPEN:
            self._handle_gvl_open(event)
        elif event.event_type == EventType.GVL_CLOSE:
            self._handle_gvl_close(event)

    def _handle_session_start(
        self, event: ParsedEvent, source_file: str
    ) -> None:
        """Handle session start event."""
        # If there's an unclosed session, finalize it as partial
        if self._current_session is not None:
            self._finalize_partial_session(source_file)

        username = event.details if event.details else "unknown"
        self._current_session = Session(
            username=username,
            start_time=event.timestamp,
            source_file=source_file,
            gvl_cycles=[],
        )
        self._current_gvl_open = None
        logger.debug("Session started for %s at %s", username, event.timestamp)

    def _handle_session_finish(
        self, event: ParsedEvent, source_file: str
    ) -> None:
        """Handle session finish event."""
        if self._current_session is None:
            logger.warning(
                "Session finish without start at %s", event.timestamp
            )
            return

        # Close any open GVL cycle (hardware guarantee, but handle gracefully)
        if self._current_gvl_open is not None:
            self._close_gvl_cycle(event.timestamp)

        session = self._current_session
        session.end_time = event.timestamp
        session.source_file = source_file

        # Calculate total duration
        if session.start_time and session.end_time:
            delta = session.end_time - session.start_time
            session.duration_seconds = delta.total_seconds()

        # Sum GVL cycles for billable time
        session.gvl_total_seconds = sum(
            c.duration_seconds for c in session.gvl_cycles
        )

        # Determine status
        if len(session.gvl_cycles) == 0:
            session.status = SessionStatus.NO_MEASUREMENT
        else:
            session.status = SessionStatus.COMPLETE

        self._sessions.append(session)
        self._current_session = None
        self._current_gvl_open = None

        logger.debug(
            "Session finished: %s, GVL total: %.1fs, cycles: %d",
            session.username,
            session.gvl_total_seconds,
            len(session.gvl_cycles),
        )

    def _handle_gvl_open(self, event: ParsedEvent) -> None:
        """Handle GVL open event - start of billable time."""
        if self._current_session is None:
            logger.warning("GVL open outside session at %s", event.timestamp)
            return

        if self._current_gvl_open is not None:
            # GVL already open - unusual but don't double-count
            logger.warning(
                "GVL open while already open at %s", event.timestamp
            )
            return

        self._current_gvl_open = event.timestamp
        logger.debug("GVL open at %s", event.timestamp)

    def _handle_gvl_close(self, event: ParsedEvent) -> None:
        """Handle GVL close event - end of billable time."""
        if self._current_session is None:
            logger.warning("GVL close outside session at %s", event.timestamp)
            return

        if self._current_gvl_open is None:
            logger.warning(
                "GVL close without open at %s", event.timestamp
            )
            return

        self._close_gvl_cycle(event.timestamp)

    def _close_gvl_cycle(self, close_time: datetime) -> None:
        """Close the current GVL cycle and add it to the session."""
        if self._current_gvl_open is None or self._current_session is None:
            return

        cycle = GVLCycle(
            open_time=self._current_gvl_open,
            close_time=close_time,
        )
        self._current_session.gvl_cycles.append(cycle)
        self._current_gvl_open = None

        logger.debug(
            "GVL cycle closed: %.1f seconds", cycle.duration_seconds
        )

    def _finalize_partial_session(self, source_file: str) -> None:
        """Finalize an unclosed session as PARTIAL."""
        if self._current_session is None:
            return

        session = self._current_session
        session.source_file = source_file
        session.status = SessionStatus.PARTIAL

        # Close any open GVL cycle using last known time
        # (not ideal but better than losing data)
        if self._current_gvl_open is not None:
            # Leave it unclosed - partial data
            self._current_gvl_open = None

        # Sum whatever GVL cycles we have
        session.gvl_total_seconds = sum(
            c.duration_seconds for c in session.gvl_cycles
        )

        if session.start_time:
            session.duration_seconds = 0.0  # Unknown end

        self._sessions.append(session)
        self._current_session = None

        logger.debug(
            "Partial session finalized: %s", session.username
        )
