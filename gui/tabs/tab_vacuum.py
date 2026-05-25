"""Vacuum tab - cycles list, penalty tracking, statistics."""

import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger(__name__)


class VacuumTab(ttk.Frame):
    """Vacuum cycles list with status, penalties, and stats."""

    def __init__(self, parent, db_manager=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db_manager
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build vacuum tab layout."""
        # Stats bar
        stats_frame = ttk.LabelFrame(self, text="Vacuum Statistics", padding=8)
        stats_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.stat_vars = {}
        stats = [("OK", "ok"), ("Aborted", "aborted"), ("LEFT_VENTED", "left_vented"),
                 ("Total Penalties (PLN)", "penalties_pln"), ("Avg Pump Time (s)", "avg_pump")]
        for i, (label, key) in enumerate(stats):
            var = tk.StringVar(value="0")
            self.stat_vars[key] = var
            ttk.Label(stats_frame, text=f"{label}:").grid(row=0, column=i*2, padx=5, sticky="e")
            ttk.Label(stats_frame, textvariable=var, font=("Segoe UI", 10, "bold")).grid(
                row=0, column=i*2+1, padx=(0, 15), sticky="w")

        # Notebook with Cycles and Penalties tabs
        sub_notebook = ttk.Notebook(self)
        sub_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Cycles sub-tab
        cycles_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(cycles_frame, text=" Cycles ")

        columns = ("id", "user", "command", "start", "end", "duration", "status", "ready_time")
        self.cycles_tree = ttk.Treeview(cycles_frame, columns=columns, show="headings")
        for col, text, w in [
            ("id", "ID", 40), ("user", "User", 100), ("command", "Command", 70),
            ("start", "Start", 140), ("end", "End", 140), ("duration", "Duration (s)", 80),
            ("status", "Status", 100), ("ready_time", "Ready (s)", 70),
        ]:
            self.cycles_tree.heading(col, text=text)
            self.cycles_tree.column(col, width=w)

        sb = ttk.Scrollbar(cycles_frame, orient=tk.VERTICAL, command=self.cycles_tree.yview)
        self.cycles_tree.configure(yscrollcommand=sb.set)
        self.cycles_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Penalties sub-tab
        penalties_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(penalties_frame, text=" Penalties ")

        pen_columns = ("id", "user", "amount", "reason", "date", "paid")
        self.penalties_tree = ttk.Treeview(penalties_frame, columns=pen_columns, show="headings")
        for col, text, w in [
            ("id", "ID", 40), ("user", "User", 120), ("amount", "Amount (PLN)", 90),
            ("reason", "Reason", 120), ("date", "Date", 150), ("paid", "Paid", 60),
        ]:
            self.penalties_tree.heading(col, text=text)
            self.penalties_tree.column(col, width=w)

        sb2 = ttk.Scrollbar(penalties_frame, orient=tk.VERTICAL, command=self.penalties_tree.yview)
        self.penalties_tree.configure(yscrollcommand=sb2.set)
        self.penalties_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)

        # Refresh button
        ttk.Button(self, text="Refresh", command=self.refresh).pack(pady=5)

    def refresh(self):
        """Reload vacuum data."""
        if not self.db:
            return

        try:
            # Stats
            row = self.db.conn.execute(
                "SELECT status, COUNT(*) FROM vacuum_cycles GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r[1] for r in row}
            self.stat_vars["ok"].set(str(counts.get("OK", 0)))
            self.stat_vars["aborted"].set(str(counts.get("ABORTED", 0)))
            self.stat_vars["left_vented"].set(str(counts.get("LEFT_VENTED", 0)))

            row = self.db.conn.execute("SELECT COALESCE(SUM(amount), 0) FROM penalties").fetchone()
            self.stat_vars["penalties_pln"].set(f"{row[0]:.0f}")

            row = self.db.conn.execute(
                "SELECT AVG(ready_time_seconds) FROM vacuum_cycles WHERE status = 'OK'"
            ).fetchone()
            self.stat_vars["avg_pump"].set(f"{row[0]:.0f}" if row[0] else "0")

            # Cycles
            for item in self.cycles_tree.get_children():
                self.cycles_tree.delete(item)

            rows = self.db.conn.execute(
                "SELECT * FROM vacuum_cycles ORDER BY start_time DESC LIMIT 200"
            ).fetchall()
            for r in rows:
                start = r["start_time"][:16] if r["start_time"] else ""
                end = r["end_time"][:16] if r["end_time"] else ""
                self.cycles_tree.insert("", tk.END, values=(
                    r["id"], r["username"], r["command"], start, end,
                    f"{r['duration_seconds']:.0f}", r["status"],
                    f"{r['ready_time_seconds']:.0f}" if r["ready_time_seconds"] else ""
                ))

            # Penalties
            for item in self.penalties_tree.get_children():
                self.penalties_tree.delete(item)

            rows = self.db.conn.execute(
                "SELECT * FROM penalties ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
            for r in rows:
                date = r["timestamp"][:16] if r["timestamp"] else ""
                self.penalties_tree.insert("", tk.END, values=(
                    r["id"], r["username"], f"{r['amount']:.0f}",
                    r["reason"], date, "Yes" if r["paid"] else "No"
                ))

        except Exception as e:
            logger.error("Error loading vacuum data: %s", e)
