"""History log parser for TESCAN VEGA3.

Parses History-YYYY-MM.log files with format:
YYYY-MM-DD HH:MM:SS.fff [I] event text
YYYY-MM-DD HH:MM:SS.fff [E] error text
"""

import re
import logging
from datetime import datetime
from typing import List, Optional, Generator

from models.enums import EventType
from models.dataclasses import ParsedEvent

logger = logging.getLogger(__name__)

# Base timestamp pattern
TIMESTAMP_RE = r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})"
LEVEL_RE = r"\[(I|E)\]"
LINE_RE = re.compile(rf"^{TIMESTAMP_RE}\s+{LEVEL_RE}\s+(.*)$")

# Event patterns - order matters for matching priority
EVENT_PATTERNS = [
    (
        re.compile(r"==\s*Session started for user:\s*(\S+)\s*==", re.IGNORECASE),
        EventType.SESSION_START,
    ),
    (
        re.compile(r"==\s*Session finished\s*==", re.IGNORECASE),
        EventType.SESSION_FINISH,
    ),
    (
        re.compile(r"HV:\s*HV has been turned ON", re.IGNORECASE),
        EventType.HV_ON,
    ),
    (
        re.compile(r"HV:\s*HV has been turned OFF", re.IGNORECASE),
        EventType.HV_OFF,
    ),
    (
        re.compile(r"HV:\s*HV heating has been turned OFF", re.IGNORECASE),
        EventType.HV_HEATING_OFF,
    ),
    (
        re.compile(r"HV:\s*HV is being turned ON", re.IGNORECASE),
        EventType.HV_TURNING_ON,
    ),
    (
        re.compile(r"HV:\s*HV is being turned OFF", re.IGNORECASE),
        EventType.HV_TURNING_OFF,
    ),
    (
        re.compile(r"Vacuum:\s*command GVL open", re.IGNORECASE),
        EventType.GVL_OPEN,
    ),
    (
        re.compile(r"Vacuum:\s*command GVL close", re.IGNORECASE),
        EventType.GVL_CLOSE,
    ),
    (
        re.compile(r"Vacuum:\s*command PUMP", re.IGNORECASE),
        EventType.PUMP,
    ),
    (
        re.compile(r"Vacuum:\s*command VENT", re.IGNORECASE),
        EventType.VENT,
    ),
    (
        re.compile(r"Vacuum:\s*command OFF", re.IGNORECASE),
        EventType.VAC_OFF,
    ),
    (
        re.compile(r"Vacuum:\s*Vacuum:\s*ready in\s+(\d+)\s*s", re.IGNORECASE),
        EventType.VAC_READY,
    ),
    (
        re.compile(r"==\s*Starting software\s*==", re.IGNORECASE),
        EventType.SOFTWARE_START,
    ),
    (
        re.compile(r"==\s*Terminating software\s*==", re.IGNORECASE),
        EventType.SOFTWARE_TERMINATE,
    ),
    (
        re.compile(r"SN:\s*(VG\S+)", re.IGNORECASE),
        EventType.SERIAL_NUMBER,
    ),
    (
        re.compile(
            r"HV:\s*Filament time:\s*(\d+)\s*h\s*(\d+)\s*min.*type:\s*(\w+)",
            re.IGNORECASE,
        ),
        EventType.FILAMENT_TIME,
    ),
    (
        re.compile(r"Vacuum:\s*Vacuum time:\s*(\d+)\s*h\s*(\d+)\s*min", re.IGNORECASE),
        EventType.VACUUM_TIME,
    ),
    (
        re.compile(r"ChamberView:\s*starting live image", re.IGNORECASE),
        EventType.CHAMBER_VIEW,
    ),
]


class HistoryLogParser:
    """Parser for VEGA3 history log files."""

    def __init__(self):
        self.errors: List[dict] = []

    def parse_file(self, file_path: str) -> List[ParsedEvent]:
        """Parse an entire history log file and return events."""
        events = []
        self.errors = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.rstrip("\n\r")
                    if not line.strip():
                        continue
                    event = self._parse_line(line, line_num, file_path)
                    if event is not None:
                        events.append(event)
        except OSError as e:
            logger.error("Failed to read file %s: %s", file_path, e)
            self.errors.append({
                "source_file": file_path,
                "line_number": 0,
                "raw_line": "",
                "error_message": str(e),
            })

        logger.info(
            "Parsed %d events from %s (%d errors)",
            len(events), file_path, len(self.errors),
        )
        return events

    def parse_file_generator(
        self, file_path: str
    ) -> Generator[ParsedEvent, None, None]:
        """Parse a history log file as a generator (memory efficient)."""
        self.errors = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.rstrip("\n\r")
                    if not line.strip():
                        continue
                    event = self._parse_line(line, line_num, file_path)
                    if event is not None:
                        yield event
        except OSError as e:
            logger.error("Failed to read file %s: %s", file_path, e)

    def _parse_line(
        self, line: str, line_num: int, file_path: str
    ) -> Optional[ParsedEvent]:
        """Parse a single log line into a ParsedEvent."""
        match = LINE_RE.match(line)
        if not match:
            self.errors.append({
                "source_file": file_path,
                "line_number": line_num,
                "raw_line": line[:500],
                "error_message": "Line does not match expected format",
            })
            return None

        timestamp_str = match.group(1)
        level = match.group(2)
        content = match.group(3)

        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError as e:
            self.errors.append({
                "source_file": file_path,
                "line_number": line_num,
                "raw_line": line[:500],
                "error_message": f"Invalid timestamp: {e}",
            })
            return None

        # Error lines
        if level == "E":
            return ParsedEvent(
                timestamp=timestamp,
                event_type=EventType.ERROR,
                raw_line=line,
                details=content,
                source_file=file_path,
                line_number=line_num,
            )

        # Match against known event patterns
        event_type, details = self._classify_event(content)

        return ParsedEvent(
            timestamp=timestamp,
            event_type=event_type,
            raw_line=line,
            details=details,
            source_file=file_path,
            line_number=line_num,
        )

    def _classify_event(self, content: str) -> tuple:
        """Classify event content into an EventType and extract details."""
        for pattern, event_type in EVENT_PATTERNS:
            m = pattern.search(content)
            if m:
                # Return matched groups as details if any
                groups = m.groups()
                details = groups[0] if len(groups) == 1 else "|".join(groups) if groups else content
                return event_type, details

        return EventType.UNKNOWN, content
