"""Help tab - displays USER_MANUAL.md in a scrollable Text widget."""

import tkinter as tk
from tkinter import ttk
import logging
import os

logger = logging.getLogger(__name__)


class HelpTab:
    """Help tab showing user manual from docs/USER_MANUAL.md."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self._build_ui()
        self._load_manual()

    def _build_ui(self):
        """Build help tab with scrollable text widget."""
        ttk.Label(self.frame, text="User Manual", font=("", 14, "bold")).pack(
            anchor=tk.W, pady=(0, 10)
        )

        # Text widget with scrollbar
        text_frame = ttk.Frame(self.frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text_widget = tk.Text(
            text_frame, wrap=tk.WORD, font=("Consolas", 10),
            state=tk.DISABLED, padx=10, pady=10,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=scrollbar.set)

        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _load_manual(self):
        """Load USER_MANUAL.md content into text widget."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manual_path = os.path.join(base_dir, "docs", "USER_MANUAL.md")

        content = self._read_manual(manual_path)

        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, content)
        self.text_widget.config(state=tk.DISABLED)

    def _read_manual(self, path):
        """Read manual file, return content or fallback message."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return (
                "User manual not found.\n\n"
                f"Expected location: {path}\n\n"
                "Please ensure docs/USER_MANUAL.md exists in the application directory."
            )
        except OSError as e:
            logger.error("Failed to read manual: %s", e)
            return f"Error reading manual: {e}"
