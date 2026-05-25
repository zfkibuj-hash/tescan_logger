"""HV/Emission log parser for TESCAN microscopes.

Parses hv-YYYY-MM.log files containing per-second measurements.
Auto-detects VEGA3 (8+1 fields) vs MIRA3_FEG (11 fields) format.
Uses generator pattern for memory-efficient processing of large files.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, Tuple, List

from models.enums import MicroscopeType
from models.hv_models import HVSample

logger = logging.getLogger(__name__)

# Timestamp prefix pattern
TIMESTAMP_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\[I\]\s+(.*)'
)


class HVLogParser:
    """Parser for HV/emission log files.

    Auto-detects format (VEGA3 vs MIRA3_FEG) by scanning first 50 data lines.
    Yields HVSample objects via generator for memory efficiency.
    """

    def __init__(self):
        self.errors: List[dict] = []
        self._detected_type: Optional[MicroscopeType] = None

    def detect_format(self, file_path: str) -> MicroscopeType:
        """Detect HV log format by scanning first 50 data lines.

        Rules:
        - 8 numeric fields + word (Open/Closed) → VEGA3
        - 11 numeric/hex fields → MIRA3_FEG

        Returns:
            Detected MicroscopeType.
        """
        path = Path(file_path)
        data_lines_seen = 0

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if data_lines_seen >= 50:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    ts_match = TIMESTAMP_PATTERN.match(line)
                    if not ts_match:
                        continue

                    data_part = ts_match.group(2).strip()
                    fields = data_part.split()

                    if not fields:
                        continue

                    data_lines_seen += 1

                    # Check for VEGA3: last field is Open or Closed, 8-9 fields
                    if fields[-1] in ("Open", "Closed") and len(fields) in (8, 9):
                        self._detected_type = MicroscopeType.VEGA3
                        return MicroscopeType.VEGA3

                    # Check for MIRA3_FEG: 11 fields, one starts with 0x
                    if len(fields) >= 11:
                        has_hex = any(f.startswith("0x") for f in fields)
                        if has_hex:
                            self._detected_type = MicroscopeType.MIRA3_FEG
                            return MicroscopeType.MIRA3_FEG

        except IOError as e:
            logger.error("Error detecting HV format for %s: %s", file_path, e)

        # Default fallback based on field count of last line seen
        logger.warning("Could not definitively detect HV format for %s, defaulting to VEGA3", file_path)
        self._detected_type = MicroscopeType.VEGA3
        return MicroscopeType.VEGA3

    def parse_file_generator(
        self, file_path: str, microscope_id: int = 0
    ) -> Generator[HVSample, None, None]:
        """Parse HV log file as generator, yielding HVSample objects.

        Args:
            file_path: Path to HV log file.
            microscope_id: ID of the microscope in the database.

        Yields:
            HVSample objects.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("HV file not found: %s", file_path)
            return

        # Detect format first
        microscope_type = self.detect_format(file_path)
        logger.info("Parsing HV file %s as %s", file_path, microscope_type.value)

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.rstrip('\n\r')
                    if not line.strip():
                        continue

                    sample = self._parse_line(
                        line, line_number, str(file_path),
                        microscope_type, microscope_id
                    )
                    if sample is not None:
                        yield sample
        except IOError as e:
            logger.error("Error reading HV file %s: %s", file_path, e)
            self.errors.append({
                "file_path": str(file_path),
                "line_number": 0,
                "error_message": f"IO error: {e}",
            })

    def _parse_line(
        self, line: str, line_number: int, source_file: str,
        microscope_type: MicroscopeType, microscope_id: int
    ) -> Optional[HVSample]:
        """Parse single HV log line into HVSample."""
        ts_match = TIMESTAMP_PATTERN.match(line)
        if not ts_match:
            return None

        timestamp_str = ts_match.group(1)
        data_part = ts_match.group(2).strip()
        fields = data_part.split()

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

        try:
            if microscope_type == MicroscopeType.VEGA3:
                return self._parse_vega3_fields(
                    fields, timestamp, source_file, microscope_id, line_number, line
                )
            else:
                return self._parse_mira3_fields(
                    fields, timestamp, source_file, microscope_id, line_number, line
                )
        except (ValueError, IndexError) as e:
            self.errors.append({
                "file_path": source_file,
                "line_number": line_number,
                "raw_line": line[:200],
                "error_message": f"Parse error: {e}",
            })
            return None

    def _parse_vega3_fields(
        self, fields: list, timestamp: datetime, source_file: str,
        microscope_id: int, line_number: int, raw_line: str
    ) -> Optional[HVSample]:
        """Parse VEGA3 HV fields (7 numeric + Open/Closed = 8, or 8 numeric + Open/Closed = 9)."""
        if len(fields) < 8:
            return None

        # Last field is valve state
        valve_state = fields[-1] if fields[-1] in ("Open", "Closed") else None
        # Numeric fields are everything except the last if it's a valve state
        num_fields = fields[:-1] if valve_state else fields

        return HVSample(
            microscope_id=microscope_id,
            timestamp=timestamp,
            source_file=source_file,
            set_hv_kv=float(num_fields[0]),
            actual_hv_kv=float(num_fields[1]),
            emission_current_ua=float(num_fields[2]),
            filament_current_a=float(num_fields[3]),
            heating_percent=float(num_fields[4]) if len(num_fields) > 4 else None,
            gun_pressure_pa=float(num_fields[5]) if len(num_fields) > 5 else 0.0,
            chamber_pressure_pa=float(num_fields[6]) if len(num_fields) > 6 else 0.0,
            gun_valve_state=valve_state,
        )

    def _parse_mira3_fields(
        self, fields: list, timestamp: datetime, source_file: str,
        microscope_id: int, line_number: int, raw_line: str
    ) -> Optional[HVSample]:
        """Parse MIRA3 FEG HV fields (11 numeric/hex)."""
        if len(fields) < 11:
            return None

        return HVSample(
            microscope_id=microscope_id,
            timestamp=timestamp,
            source_file=source_file,
            set_hv_kv=float(fields[0]),
            extractor_voltage_kv=float(fields[1]),
            suppressor_voltage_v=float(fields[2]),
            total_current_ua=float(fields[3]),
            emission_current_ua=float(fields[4]),
            filament_current_a=float(fields[5]),
            flags_hex=fields[6],
            gun_pressure_pa=float(fields[7]),
            actual_hv_kv=float(fields[8]),
            column_ion_pump_pressure_pa=float(fields[9]),
            chamber_pressure_pa=float(fields[10]),
        )

    def get_errors(self) -> List[dict]:
        """Get list of parsing errors."""
        return self.errors.copy()

    def clear_errors(self) -> None:
        """Clear stored errors."""
        self.errors.clear()
