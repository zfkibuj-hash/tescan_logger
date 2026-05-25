"""Sessions tab - Treeview with filters, PPM right-click menu with audit."""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import logging

logger = logging.getLogger(__name__)


class SessionsTab:
    """Sessions list with filters and per-session PPM context menu."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build sessions tab layout."""
        # Filter bar
        filter_frame = ttk.Frame(self.frame)
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_frame, text="User:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_user = ttk.Combobox(filter_frame, width=15, state="readonly")
        self.filter_user.pack(side=tk.LEFT, padx=(0, 10))
        self.filter_user.set("")

        ttk.Label(filter_frame, text="Status:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_status = ttk.Combobox(
            filter_frame, width=15, state="readonly",
            values=["", "COMPLETE", "NO_MEASUREMENT", "PARTIAL", "CANCELLED"],
        )
        self.filter_status.pack(side=tk.LEFT, padx=(0, 10))
        self.filter_status.set("")

        ttk.Button(filter_frame, text="Apply Filter", command=self.refresh).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(filter_frame, text="Clear", command=self._clear_filters).pack(
            side=tk.LEFT, padx=5
        )

        # Sessions treeview
        cols = (
            "id", "user", "start", "end", "duration", "gvl_time",
            "gvl_cycles", "status", "discount", "cost",
        )
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=20)
        self.tree.heading("id", text="ID")
        self.tree.heading("user", text="User")
        self.tree.heading("start", text="Start Time")
        self.tree.heading("end", text="End Time")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("gvl_time", text="GVL Time")
        self.tree.heading("gvl_cycles", text="GVL Cycles")
        self.tree.heading("status", text="Status")
        self.tree.heading("discount", text="Discount %")
        self.tree.heading("cost", text="Cost (PLN)")

        self.tree.column("id", width=40)
        self.tree.column("user", width=100)
        self.tree.column("start", width=150)
        self.tree.column("end", width=150)
        self.tree.column("duration", width=80)
        self.tree.column("gvl_time", width=80)
        self.tree.column("gvl_cycles", width=70)
        self.tree.column("status", width=110)
        self.tree.column("discount", width=80)
        self.tree.column("cost", width=90)

        vsb = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(self.frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # PPM right-click menu
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Set Discount %", command=self._set_discount)
        self.context_menu.add_command(label="Set Fixed Cost (PLN)", command=self._set_fixed_cost)
        self.context_menu.add_command(label="Set Manual Time (min)", command=self._set_manual_time)
        self.context_menu.add_command(label="Subtract Hours from Billing", command=self._subtract_hours)
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Exclude from Invoice (toggle)", command=self._toggle_exclude
        )
        self.context_menu.add_command(label="Cancel Session", command=self._cancel_session)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Show HV Chart", command=self._show_hv_chart)

        self.tree.bind("<Button-3>", self._show_context_menu)

    def refresh(self):
        """Refresh sessions list with current filters."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        username = self.filter_user.get() or None
        status = self.filter_status.get() or None

        try:
            sessions = self.app.session_repo.get_all(username=username, status=status)
            for s in sessions:
                dur = s.get("duration_seconds", 0)
                dur_str = f"{int(dur // 60)}m {int(dur % 60)}s"
                gvl = s.get("gvl_total_seconds", 0)
                gvl_str = f"{int(gvl // 60)}m {int(gvl % 60)}s"
                start = s.get("start_time", "")
                if start and len(start) > 19:
                    start = start[:19]
                end = s.get("end_time", "")
                if end and len(end) > 19:
                    end = end[:19]
                self.tree.insert("", tk.END, values=(
                    s["id"], s.get("username", ""), start, end,
                    dur_str, gvl_str, s.get("gvl_cycle_count", 0),
                    s.get("status", ""), s.get("discount_percent", 0),
                    f"{s.get('cost', 0):.2f}",
                ))
            # Update user filter options
            users = sorted(set(s.get("username", "") for s in sessions))
            self.filter_user["values"] = [""] + users
        except Exception as e:
            logger.error("Failed to load sessions: %s", e)

    def _clear_filters(self):
        """Clear all filters and refresh."""
        self.filter_user.set("")
        self.filter_status.set("")
        self.refresh()

    def _get_selected_session_id(self):
        """Get the ID of the currently selected session."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a session first.")
            return None
        item = self.tree.item(selected[0])
        return int(item["values"][0])

    def _show_context_menu(self, event):
        """Show PPM context menu on right-click."""
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _set_discount(self):
        """Set discount percentage for session (PPM)."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        value = simpledialog.askfloat(
            "Set Discount", "Discount percentage (0-100):", minvalue=0, maxvalue=100
        )
        if value is None:
            return
        operator = self.app.get_operator()
        self.app.session_repo.update_discount(session_id, value, operator)
        self._recalculate_cost(session_id)
        self.refresh()
        self.app.set_status(f"Discount set to {value}% for session {session_id}")

    def _set_fixed_cost(self):
        """Set fixed cost in PLN for session (PPM)."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        value = simpledialog.askfloat("Set Fixed Cost", "Cost in PLN:", minvalue=0)
        if value is None:
            return
        operator = self.app.get_operator()
        self.app.session_repo.override_cost(session_id, value, operator)
        self.refresh()
        self.app.set_status(f"Fixed cost {value} PLN set for session {session_id}")

    def _set_manual_time(self):
        """Set manual billable time in minutes (PPM)."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        value = simpledialog.askfloat("Set Manual Time", "Billable time (minutes):", minvalue=0)
        if value is None:
            return
        operator = self.app.get_operator()
        self.app.session_repo.override_time(session_id, value, operator)
        self._recalculate_cost(session_id)
        self.refresh()

    def _subtract_hours(self):
        """Subtract hours from billable time (PPM).

        Example: session has 12h GVL time, user subtracts 2h -> billed for 10h.
        Preserves original measurement time, records discount_hours separately.
        """
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        session = self.app.session_repo.get_by_id(session_id)
        if session is None:
            return
        gvl_hours = session.get("gvl_total_seconds", 0) / 3600.0
        value = simpledialog.askfloat(
            "Subtract Hours",
            f"Hours to subtract from billing (measured: {gvl_hours:.1f}h):",
            minvalue=0, maxvalue=gvl_hours,
        )
        if value is None:
            return
        operator = self.app.get_operator()
        self.app.session_repo.set_discount_hours(session_id, value, operator)
        self._recalculate_cost(session_id)
        self.refresh()
        self.app.set_status(
            f"Subtracted {value}h from session {session_id} "
            f"(was {gvl_hours:.1f}h, billed for {gvl_hours - value:.1f}h)"
        )
        self.app.set_status(f"Manual time {value} min set for session {session_id}")

    def _toggle_exclude(self):
        """Toggle exclude from invoice flag (PPM)."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        session = self.app.session_repo.get_by_id(session_id)
        if session is None:
            return
        current = bool(session.get("excluded_from_billing", 0))
        operator = self.app.get_operator()
        self.app.session_repo.exclude_from_billing(session_id, not current, operator)
        self.refresh()
        state = "excluded" if not current else "included"
        self.app.set_status(f"Session {session_id} {state} from billing")

    def _cancel_session(self):
        """Cancel session - set cost to 0 and status CANCELLED (PPM)."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        confirm = messagebox.askyesno(
            "Cancel Session", f"Cancel session {session_id}? Cost will be set to 0."
        )
        if not confirm:
            return
        operator = self.app.get_operator()
        self.app.session_repo.cancel_session(session_id, operator)
        self.refresh()
        self.app.set_status(f"Session {session_id} cancelled")

    def _show_hv_chart(self):
        """Switch to HV Charts tab and show data for selected session."""
        session_id = self._get_selected_session_id()
        if session_id is None:
            return
        session = self.app.session_repo.get_by_id(session_id)
        if session is None:
            return
        # Switch to HV Charts tab and load session time range
        self.app.notebook.select(4)  # HV Charts is tab index 4
        start = session.get("start_time", "")
        end = session.get("end_time", "")
        if start and end:
            self.app.tab_hv_charts.load_session_range(start, end)

    def _recalculate_cost(self, session_id):
        """Recalculate session cost after PPM change."""
        try:
            from models.dataclasses import Session
            from models.enums import SessionStatus
            session_data = self.app.session_repo.get_by_id(session_id)
            if not session_data:
                return
            session = Session(
                id=session_data["id"],
                gvl_total_seconds=session_data.get("gvl_total_seconds", 0),
                discount_percent=session_data.get("discount_percent", 0),
                override_cost=session_data.get("override_cost"),
                override_time_minutes=session_data.get("override_time_minutes"),
                excluded_from_billing=bool(session_data.get("excluded_from_billing", 0)),
            )
            cost = self.app.billing_service.calculate_session_cost(session)
            with self.app.db.get_cursor() as cursor:
                cursor.execute("UPDATE sessions SET cost = ? WHERE id = ?", (cost, session_id))
        except Exception as e:
            logger.error("Failed to recalculate cost: %s", e)
