"""Vacuum tab - cycles list, penalties list, anomalies list, stats summary."""

import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger(__name__)


class VacuumTab:
    """Vacuum cycles, penalties, anomalies with summary stats."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build vacuum tab layout."""
        # Stats summary at top
        self.stats_frame = ttk.LabelFrame(self.frame, text="Summary", padding=5)
        self.stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.stat_vars = {}
        stat_names = [
            "Total Cycles", "OK Cycles", "Aborted", "Left Vented",
            "Total Penalties (PLN)", "Anomalies",
        ]
        for i, name in enumerate(stat_names):
            lbl = ttk.Label(self.stats_frame, text=f"{name}: 0", font=("", 10))
            lbl.grid(row=0, column=i, padx=10, sticky="w")
            self.stat_vars[name] = lbl

        # Paned window for three lists
        paned = ttk.PanedWindow(self.frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Vacuum cycles list
        cycles_frame = ttk.LabelFrame(paned, text="Vacuum Cycles", padding=5)
        paned.add(cycles_frame, weight=2)

        cycle_cols = ("id", "session_id", "pump_start", "ready_time", "end_time", "status", "pump_duration")
        self.cycles_tree = ttk.Treeview(cycles_frame, columns=cycle_cols, show="headings", height=8)
        self.cycles_tree.heading("id", text="ID")
        self.cycles_tree.heading("session_id", text="Session")
        self.cycles_tree.heading("pump_start", text="Pump Start")
        self.cycles_tree.heading("ready_time", text="Ready Time")
        self.cycles_tree.heading("end_time", text="End Time")
        self.cycles_tree.heading("status", text="Status")
        self.cycles_tree.heading("pump_duration", text="Pump Duration")
        self.cycles_tree.column("id", width=40)
        self.cycles_tree.column("session_id", width=60)
        self.cycles_tree.column("pump_start", width=150)
        self.cycles_tree.column("ready_time", width=150)
        self.cycles_tree.column("end_time", width=150)
        self.cycles_tree.column("status", width=100)
        self.cycles_tree.column("pump_duration", width=100)

        csb = ttk.Scrollbar(cycles_frame, orient=tk.VERTICAL, command=self.cycles_tree.yview)
        self.cycles_tree.configure(yscrollcommand=csb.set)
        self.cycles_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        csb.pack(side=tk.RIGHT, fill=tk.Y)

        # Penalties list
        penalties_frame = ttk.LabelFrame(paned, text="Penalties", padding=5)
        paned.add(penalties_frame, weight=1)

        pen_cols = ("id", "username", "penalty_type", "amount", "timestamp", "notes")
        self.penalties_tree = ttk.Treeview(
            penalties_frame, columns=pen_cols, show="headings", height=5
        )
        self.penalties_tree.heading("id", text="ID")
        self.penalties_tree.heading("username", text="User")
        self.penalties_tree.heading("penalty_type", text="Type")
        self.penalties_tree.heading("amount", text="Amount (PLN)")
        self.penalties_tree.heading("timestamp", text="Timestamp")
        self.penalties_tree.heading("notes", text="Notes")
        self.penalties_tree.column("id", width=40)
        self.penalties_tree.column("username", width=100)
        self.penalties_tree.column("penalty_type", width=120)
        self.penalties_tree.column("amount", width=100)
        self.penalties_tree.column("timestamp", width=150)
        self.penalties_tree.column("notes", width=200)

        psb = ttk.Scrollbar(penalties_frame, orient=tk.VERTICAL, command=self.penalties_tree.yview)
        self.penalties_tree.configure(yscrollcommand=psb.set)
        self.penalties_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        psb.pack(side=tk.RIGHT, fill=tk.Y)

        # Anomalies list
        anomalies_frame = ttk.LabelFrame(paned, text="Anomalies (LONG_PUMP_TIME, IDLE_AFTER_READY)", padding=5)
        paned.add(anomalies_frame, weight=1)

        anom_cols = ("id", "type", "session_id", "timestamp", "duration", "severity", "description")
        self.anomalies_tree = ttk.Treeview(
            anomalies_frame, columns=anom_cols, show="headings", height=5
        )
        self.anomalies_tree.heading("id", text="ID")
        self.anomalies_tree.heading("type", text="Type")
        self.anomalies_tree.heading("session_id", text="Session")
        self.anomalies_tree.heading("timestamp", text="Timestamp")
        self.anomalies_tree.heading("duration", text="Duration (s)")
        self.anomalies_tree.heading("severity", text="Severity")
        self.anomalies_tree.heading("description", text="Description")
        self.anomalies_tree.column("id", width=40)
        self.anomalies_tree.column("type", width=130)
        self.anomalies_tree.column("session_id", width=60)
        self.anomalies_tree.column("timestamp", width=150)
        self.anomalies_tree.column("duration", width=90)
        self.anomalies_tree.column("severity", width=70)
        self.anomalies_tree.column("description", width=300)

        asb = ttk.Scrollbar(anomalies_frame, orient=tk.VERTICAL, command=self.anomalies_tree.yview)
        self.anomalies_tree.configure(yscrollcommand=asb.set)
        self.anomalies_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        asb.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh(self):
        """Refresh all vacuum data."""
        self._load_cycles()
        self._load_penalties()
        self._load_anomalies()
        self._update_stats()

    def _load_cycles(self):
        """Load vacuum cycles into treeview."""
        for item in self.cycles_tree.get_children():
            self.cycles_tree.delete(item)
        try:
            cycles = self.app.vacuum_repo.get_all()
            for c in cycles:
                dur = c.get("pump_duration_seconds", 0)
                dur_str = f"{int(dur)}s" if dur else "-"
                self.cycles_tree.insert("", tk.END, values=(
                    c["id"], c.get("session_id", ""),
                    (c.get("pump_start") or "")[:19],
                    (c.get("ready_time") or "")[:19],
                    (c.get("end_time") or "")[:19],
                    c.get("status", ""), dur_str,
                ))
        except Exception as e:
            logger.error("Failed to load vacuum cycles: %s", e)

    def _load_penalties(self):
        """Load penalties into treeview."""
        for item in self.penalties_tree.get_children():
            self.penalties_tree.delete(item)
        try:
            penalties = self.app.penalty_repo.get_all()
            for p in penalties:
                self.penalties_tree.insert("", tk.END, values=(
                    p["id"], p.get("username", ""),
                    p.get("penalty_type", ""), p.get("amount_pln", 100),
                    (p.get("timestamp") or "")[:19], p.get("notes", ""),
                ))
        except Exception as e:
            logger.error("Failed to load penalties: %s", e)

    def _load_anomalies(self):
        """Load anomalies into treeview."""
        for item in self.anomalies_tree.get_children():
            self.anomalies_tree.delete(item)
        try:
            anomalies = self.app.anomaly_repo.get_all()
            for a in anomalies:
                self.anomalies_tree.insert("", tk.END, values=(
                    a["id"], a.get("anomaly_type", ""),
                    a.get("session_id", ""),
                    (a.get("timestamp") or "")[:19],
                    f"{a.get('duration_seconds', 0):.0f}",
                    a.get("severity", ""), a.get("description", ""),
                ))
        except Exception as e:
            logger.error("Failed to load anomalies: %s", e)

    def _update_stats(self):
        """Update summary statistics."""
        try:
            db = self.app.db
            with db.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles")
                total = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles WHERE status = 'OK'")
                ok = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles WHERE status = 'ABORTED'")
                aborted = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles WHERE status = 'LEFT_VENTED'")
                vented = cursor.fetchone()["cnt"]
                cursor.execute("SELECT COALESCE(SUM(amount_pln), 0) as s FROM penalties")
                pen_total = cursor.fetchone()["s"]
                cursor.execute("SELECT COUNT(*) as cnt FROM anomalies")
                anom = cursor.fetchone()["cnt"]

            self.stat_vars["Total Cycles"].config(text=f"Total Cycles: {total}")
            self.stat_vars["OK Cycles"].config(text=f"OK Cycles: {ok}")
            self.stat_vars["Aborted"].config(text=f"Aborted: {aborted}")
            self.stat_vars["Left Vented"].config(text=f"Left Vented: {vented}")
            self.stat_vars["Total Penalties (PLN)"].config(text=f"Total Penalties: {pen_total:.0f} PLN")
            self.stat_vars["Anomalies"].config(text=f"Anomalies: {anom}")
        except Exception as e:
            logger.error("Failed to update vacuum stats: %s", e)
