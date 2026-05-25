"""Help tab - displays user manual content."""

import tkinter as tk
from tkinter import ttk
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class HelpTab(ttk.Frame):
    """Help tab - renders user manual in a scrollable text widget."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self):
        """Build help tab with manual content."""
        ttk.Label(self, text="TESCAN Log Analyzer - User Manual",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Text widget with scrollbar
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10),
                           padx=10, pady=10, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load manual
        self._load_manual()

    def _load_manual(self):
        """Load USER_MANUAL.md content."""
        manual_paths = [
            Path(__file__).parent.parent.parent / "docs" / "USER_MANUAL.md",
            Path("docs/USER_MANUAL.md"),
        ]

        content = "User manual not found."
        for path in manual_paths:
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    break
                except IOError:
                    continue

        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.text.config(state=tk.DISABLED)
