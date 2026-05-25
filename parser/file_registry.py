"""File registry for detecting and filtering log files.

Handles:
- File type detection (HISTORY vs HV)
- Include/exclude pattern matching
- File hash computation for incremental import
"""

import re
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from models.enums import FileType

logger = logging.getLogger(__name__)

# Default patterns - match standard TESCAN filenames and common variants
HISTORY_PATTERN = re.compile(
    r'(?:History-\d{4}-\d{2}\.log$)|(?:.*history.*\.log$)',
    re.IGNORECASE
)
HV_PATTERN = re.compile(
    r'(?:hv[-_].*\d{4}[-_]\d{2}.*\.log$)|(?:.*hv.*\.log$)',
    re.IGNORECASE
)


class FileRegistry:
    """File detection, filtering, and hash management.

    Provides methods to:
    - Detect file type (HISTORY / HV / UNKNOWN)
    - Scan directories with include/exclude patterns
    - Compute file hashes for duplicate detection
    """

    def __init__(
        self,
        include_history: bool = True,
        include_hv: bool = True,
        include_pattern: Optional[str] = None,
        exclude_pattern: Optional[str] = None,
    ):
        self.include_history = include_history
        self.include_hv = include_hv
        self._include_re = re.compile(include_pattern) if include_pattern else None
        self._exclude_re = re.compile(exclude_pattern) if exclude_pattern else None

    @staticmethod
    def detect_file_type(file_path: str) -> FileType:
        """Detect type of a log file by filename pattern.

        Args:
            file_path: Path or filename to check.

        Returns:
            FileType.HISTORY, FileType.HV, or FileType.UNKNOWN
        """
        name = Path(file_path).name
        if HISTORY_PATTERN.search(name):
            return FileType.HISTORY
        if HV_PATTERN.search(name):
            return FileType.HV
        return FileType.UNKNOWN

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file for duplicate detection.

        Uses 64KB chunks for memory efficiency on large HV files.
        """
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except IOError as e:
            logger.error("Cannot hash file %s: %s", file_path, e)
            return ""

    def scan_directory(self, directory: str, recursive: bool = True) -> List[Tuple[str, FileType]]:
        """Scan directory for log files matching patterns.

        Args:
            directory: Root directory to scan.
            recursive: Whether to scan subdirectories.

        Returns:
            List of (file_path, file_type) tuples.
        """
        root = Path(directory)
        if not root.is_dir():
            logger.error("Not a directory: %s", directory)
            return []

        results = []
        pattern = "**/*" if recursive else "*"

        for path in root.glob(pattern):
            if not path.is_file():
                continue

            file_path_str = str(path)

            # Apply exclude pattern
            if self._exclude_re and self._exclude_re.search(path.name):
                continue

            # Apply include pattern (if set, file must match)
            if self._include_re and not self._include_re.search(path.name):
                continue

            # Detect type
            file_type = self.detect_file_type(file_path_str)

            # Apply type toggles
            if file_type == FileType.HISTORY and not self.include_history:
                continue
            if file_type == FileType.HV and not self.include_hv:
                continue
            if file_type == FileType.UNKNOWN:
                continue

            results.append((file_path_str, file_type))

        # Sort by filename for deterministic order
        results.sort(key=lambda x: x[0])
        logger.info("Found %d files in %s", len(results), directory)
        return results

    def filter_files(self, file_paths: List[str]) -> List[Tuple[str, FileType]]:
        """Filter a list of file paths by type and patterns.

        Used for manually added files (Add Files... button).
        Manual files skip include pattern but still check type.
        """
        results = []
        for fp in file_paths:
            file_type = self.detect_file_type(fp)

            if file_type == FileType.HISTORY and not self.include_history:
                continue
            if file_type == FileType.HV and not self.include_hv:
                continue

            # For manually added files, accept even UNKNOWN type
            results.append((fp, file_type))

        return results
