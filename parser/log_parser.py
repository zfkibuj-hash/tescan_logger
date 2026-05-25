"""History log parser for TESCAN microscopes.

Parses History-YYYY-MM.log files to extract session events, vacuum commands,
and HV state changes. Uses regex pattern matching on each line.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Generator

from models.enums import EventType, MicroscopeType
from models.dataclasses import ParsedEvent

logger = logging.getLogger(__name__)

# Timestamp pattern: 2026-05-05 15:51:27.416 [I]
TIMESTAMP_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\[I\]\s+(.*)'
)

# Event patterns
EVENT_PATTERNS = {
    EventType.SESSION_START: re.compile(
        r'==\s*Session started for user:\s*(.+?)\s*=='
    ),
    EventType.SESSION_END: re.compile(
        r'==\s*Session finished\s*=='
    ),
    EventType.HV_ON: re.compile(
        r'HV:\s*HV has been turned ON'
    ),
    EventType.HV_OFF: re.compile(
        r'HV:\s*HV has been turned OFF'
    ),
    EventType.FILAMENT_OFF: re.compile(
        r'HV:\s*HV heating has been turned OFF'
    ),
    EventType.GVL_OPEN: re.compile(
        r'Vacuum:\s*command GVL open'
    ),
    EventType.GVL_CLOSE: re.compile(
        r'Vacuum:\s*command GVL close'
    ),
    EventType.VACUUM_PUMP: re.compile(
        r'Vacuum:\s*command PUMP'
    ),
    EventType.VACUUM_VENT: re.compile(
        r'Vacuum:\s*command VENT'
    ),
    EventType.VACUUM_OFF: re.compile(
        r'Vacuum:\s*command OFF'
    ),
    EventType.VACUUM_READY: re.compile(
        r'Vacuum:\s*(?:Vacuum:\s*)?ready in\s+(\d+)\s*s'
    ),
    EventType.SOFTWARE_START: re.compile(
        r'==\s*Starting software\s*=='
    ),
    EventType.SOFTWARE_TERMINATE: re.compile(
        r'==\s*Terminating software\s*=='
    ),
}


class HistoryLogParser:
    """Parser for History-YYYY-MM.log files.

    Extracts structured events from TESCAN history log files.
    Auto-detects microscope type based on event patterns found.
    """

    def __init__(self):
        self.errors: List[dict] = []

    def parse_file(self, file_path: str) -> List[ParsedEvent]:
        """Parse entire History log file into list of events.

        Args:
            file_path: Path to the History log file.

        Returns:
            List of ParsedEvent objects in chronological order.
        """
        events = list(self.parse_file_generator(file_path))
        logger.info("Parsed %d events from %s", len(events), file_path)
        return events

    def parse_file_generator(self, file_path: str) -> Generator[ParsedEvent, None, None]:
        """Parse History log file as a generator (memory efficient).

        Yields ParsedEvent objects one by one.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", file_path)
            return

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.rstrip('\n\r')
                    if not line.strip():
                        continue

                    event = self._parse_line(line, line_number, str(file_path))
                    if event is not None:
                        yield event
        except IOError as e:
            logger.error("Error reading file %s: %s", file_path, e)
            self.errors.append({
                "file_path": str(file_path),
                "line_number": 0,
                "error_message": f"IO error: {e}",
            })

    def _parse_line(self, line: str, line_number: int, source_file: str) -> ParsedEvent | None:
        """Parse a single log line into a ParsedEvent or None."""
        # Extract timestamp and content
        ts_match = TIMESTAMP_PATTERN.match(line)
        if not ts_match:
            return None

        timestamp_str = ts_match.group(1)
        content = ts_match.group(2)

        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            self.errors.append({
                "file_path": source_file,
                "line_number": line_number,
                "raw_line": line[:200],
                "error_message": f"Invalid timestamp: {timestamp_str}",
            })
            return None

        # Match against event patterns
        for event_type, pattern in EVENT_PATTERNS.items():
            match = pattern.search(content)
            if match:
                username = None
                details = None

                if event_type == EventType.SESSION_START:
                    username = match.group(1).strip()
                elif event_type == EventType.VACUUM_READY:
                    details = match.group(1)  # ready time in seconds

                return ParsedEvent(
                    timestamp=timestamp,
                    event_type=event_type,
                    raw_line=line,
                    username=username,
                    details=details,
                    line_number=line_number,
                    source_file=source_file,
                )

        return None

    def detect_microscope_type(self, events: List[ParsedEvent]) -> MicroscopeType:
        """Auto-detect microscope type from parsed events.

        Rules:
        - Presence of GVL_OPEN or GVL_CLOSE -> MIRA3_FEG
        - Presence of HV_ON without GVL events -> VEGA3
        """
        has_gvl = any(
            e.event_type in (EventType.GVL_OPEN, EventType.GVL_CLOSE)
            for e in events
        )
        if has_gvl:
            return MicroscopeType.MIRA3_FEG
        return MicroscopeType.VEGA3

    def get_errors(self) -> List[dict]:
        """Get list of parsing errors encountered."""
        return self.errors.copy()

    def clear_errors(self) -> None:
        """Clear stored parsing errors."""
        self.errors.clear()
