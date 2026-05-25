"""HV data log parser for TESCAN VEGA3.

Parses hv-YYYY-MM.log files with format:
YYYY-MM-DD HH:MM:SS.fff [I]  set_hv  actual_hv  emission  emitter  heating  gun_p  chamber_p  Open/Closed

7 numeric columns + 1 valve state (Open/Closed).
Uses generator pattern for memory efficiency with large files.
"""

import re
import logging
from datetime import datetime
from typing import List, Generator, Optional

from models.dataclasses import HVSample

logger = logging.getLogger(__name__)

# Line format: timestamp [I] followed by 7 floats and Open/Closed
HV_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\[I\]\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"([\d.eE+\-]+)\s+"
    r"(Open|Closed)\s*$"
)

# Batch size for database inserts
DEFAULT_BATCH_SIZE = 5000


class HVLogParser:
    """Parser for VEGA3 HV data log files."""

    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size
        self.errors: List[dict] = []
        self.total_samples: int = 0

    def parse_file_generator(
        self, file_path: str
    ) -> Generator[HVSample, None, None]:
        """Parse HV log file yielding one sample at a time."""
        self.errors = []
        self.total_samples = 0

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.rstrip("\n\r")
                    if not line.strip():
                        continue
                    sample = self._parse_line(line, line_num, file_path)
                    if sample is not None:
                        self.total_samples += 1
                        yield sample
        except OSError as e:
            logger.error("Failed to read HV file %s: %s", file_path, e)
            self.errors.append({
                "source_file": file_path,
                "line_number": 0,
                "raw_line": "",
                "error_message": str(e),
            })

    def parse_file_batches(
        self, file_path: str
    ) -> Generator[List[HVSample], None, None]:
        """Parse HV log file yielding batches of samples for bulk insert."""
        batch: List[HVSample] = []

        for sample in self.parse_file_generator(file_path):
            batch.append(sample)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []

        # Yield remaining samples
        if batch:
            yield batch

    def parse_file(self, file_path: str) -> List[HVSample]:
        """Parse entire HV log file into memory. Use for small files only."""
        return list(self.parse_file_generator(file_path))

    def _parse_line(
        self, line: str, line_num: int, file_path: str
    ) -> Optional[HVSample]:
        """Parse a single HV data line into an HVSample."""
        match = HV_LINE_RE.match(line)
        if not match:
            # Only log error for non-empty, non-comment lines
            if line.strip() and not line.startswith("#"):
                self.errors.append({
                    "source_file": file_path,
                    "line_number": line_num,
                    "raw_line": line[:500],
                    "error_message": "Line does not match HV data format",
                })
            return None

        timestamp_str = match.group(1)

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

        try:
            sample = HVSample(
                timestamp=timestamp,
                set_hv_kv=float(match.group(2)),
                actual_hv_kv=float(match.group(3)),
                emission_current_ua=float(match.group(4)),
                emitter_current_a=float(match.group(5)),
                heating_percent=float(match.group(6)),
                gun_pressure_pa=float(match.group(7)),
                chamber_pressure_pa=float(match.group(8)),
                gun_valve_state=match.group(9),
                source_file=file_path,
            )
            return sample
        except (ValueError, IndexError) as e:
            self.errors.append({
                "source_file": file_path,
                "line_number": line_num,
                "raw_line": line[:500],
                "error_message": f"Failed to parse numeric values: {e}",
            })
            return None

    def is_batch_ready(self, current_batch: List[HVSample]) -> bool:
        """Check if the current batch is ready for database insert."""
        return len(current_batch) >= self.batch_size
