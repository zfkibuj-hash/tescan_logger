"""Settings tab - users, microscopes, billing tiers, backup, preferences."""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import logging

logger = logging.getLogger(__name__)


class SettingsTab(ttk.Frame):
    """Settings management: users, microscopes, billing, backup."""

    def __init__(self, parent, db_manager=None, current_user_var=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db_manager
        self.current_user_var = current_user_var or tk.StringVar(value="admin")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build settings layout with sub-notebook."""
        sub_notebook = ttk.Notebook(self)
        sub_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Users sub-tab
        self._build_users_tab(sub_notebook)
        # Microscopes sub-tab
        self._build_microscopes_tab(sub_notebook)
        # Billing sub-tab
        self._build_billing_tab(sub_notebook)
        # Backup sub-tab
        self._build_backup_tab(sub_notebook)

    def _build_users_tab(self, notebook):
        """Build users management sub-tab."""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" Users ")

        # Users list
        columns = ("id", "username", "display_name", "role", "discount", "excluded")
        self.users_tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for col, text, w in [
            ("id", "ID", 30), ("username", "Username", 120),
            ("display_name", "Display Name", 150), ("role", "Role", 80),
            ("discount", "Discount %", 80), ("excluded", "Excl. Billing", 80),
        ]:
            self.users_tree.heading(col, text=text)
            self.users_tree.column(col, width=w)
        self.users_tree.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Add User", command=self._add_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Set Discount", command=self._set_user_discount).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Toggle Billing Exclusion", command=self._toggle_billing).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.RIGHT, padx=5)

    def _build_microscopes_tab(self, notebook):
        """Build microscopes management sub-tab."""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" Microscopes ")

        columns = ("id", "name", "serial", "type", "location")
        self.micro_tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        for col, text, w in [
            ("id", "ID", 30), ("name", "Name", 150),
            ("serial", "Serial Number", 150), ("type", "Type (immutable)", 120),
            ("location", "Location", 120),
        ]:
            self.micro_tree.heading(col, text=text)
            self.micro_tree.column(col, width=w)
        self.micro_tree.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Register Microscope", command=self._add_microscope).pack(side=tk.LEFT, padx=5)

        # Rates section
        rates_frame = ttk.LabelFrame(frame, text="Billing Rates (per microscope per tier)", padding=5)
        rates_frame.pack(fill=tk.X, pady=5)

        rate_cols = ("microscope", "tier", "rate")
        self.rates_tree = ttk.Treeview(rates_frame, columns=rate_cols, show="headings", height=6)
        self.rates_tree.heading("microscope", text="Microscope")
        self.rates_tree.heading("tier", text="Tier")
        self.rates_tree.heading("rate", text="Rate (PLN/h)")
        self.rates_tree.column("microscope", width=150)
        self.rates_tree.column("tier", width=100)
        self.rates_tree.column("rate", width=100)
        self.rates_tree.pack(fill=tk.X)

        ttk.Button(rates_frame, text="Edit Rate", command=self._edit_rate).pack(pady=3)

    def _build_billing_tab(self, notebook):
        """Build billing settings sub-tab."""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" Billing ")

        ttk.Label(frame, text="Billing Configuration", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Default rates are set per microscope in the Microscopes tab.").pack(anchor="w", pady=5)
        ttk.Label(frame, text="Penalty amount for LEFT_VENTED: 100 PLN (fixed)").pack(anchor="w")
        ttk.Label(frame, text="Discount reduces TIME, not rate.").pack(anchor="w")
        ttk.Label(frame, text="Tiers: PROJECT / UJ_UNIT / EXTERNAL").pack(anchor="w")

    def _build_backup_tab(self, notebook):
        """Build backup management sub-tab."""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" Backup ")

        ttk.Label(frame, text="Database Backup", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Button(frame, text="Create Backup Now", command=self._backup_now).pack(anchor="w", pady=5)
        ttk.Button(frame, text="Verify DB Integrity", command=self._verify_integrity).pack(anchor="w", pady=5)

        self.backup_status = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.backup_status).pack(anchor="w", pady=10)

        # Backup list
        ttk.Label(frame, text="Existing Backups:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 5))
        self.backup_list = tk.Listbox(frame, height=8)
        self.backup_list.pack(fill=tk.X, pady=5)

    def refresh(self):
        """Refresh all settings data."""
        if not self.db:
            return
        self._load_users()
        self._load_microscopes()
        self._load_rates()
        self._load_backups()

    def _load_users(self):
        """Load users into treeview."""
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        try:
            rows = self.db.conn.execute("SELECT * FROM users ORDER BY username").fetchall()
            for r in rows:
                self.users_tree.insert("", tk.END, iid=str(r["id"]), values=(
                    r["id"], r["username"], r["display_name"] or "",
                    r["role"], r["discount_percent"] or 0,
                    "Yes" if r["excluded_from_billing"] else "No"
                ))
        except Exception as e:
            logger.error("Error loading users: %s", e)

    def _load_microscopes(self):
        """Load microscopes into treeview."""
        for item in self.micro_tree.get_children():
            self.micro_tree.delete(item)
        try:
            rows = self.db.conn.execute("SELECT * FROM microscopes ORDER BY name").fetchall()
            for r in rows:
                self.micro_tree.insert("", tk.END, iid=str(r["id"]), values=(
                    r["id"], r["name"], r["serial_number"],
                    r["microscope_type"], r["location"] or ""
                ))
        except Exception as e:
            logger.error("Error loading microscopes: %s", e)

    def _load_rates(self):
        """Load billing tier rates."""
        for item in self.rates_tree.get_children():
            self.rates_tree.delete(item)
        try:
            rows = self.db.conn.execute("""
                SELECT m.name, bt.tier_name, bt.rate_pln_per_hour, bt.id
                FROM billing_tiers bt JOIN microscopes m ON bt.microscope_id = m.id
                ORDER BY m.name, bt.tier_name
            """).fetchall()
            for r in rows:
                self.rates_tree.insert("", tk.END, iid=str(r["id"]), values=(
                    r["name"], r["tier_name"], f"{r['rate_pln_per_hour']:.0f}"
                ))
        except Exception as e:
            logger.error("Error loading rates: %s", e)

    def _load_backups(self):
        """Load backup list."""
        self.backup_list.delete(0, tk.END)
        try:
            from utils.backup import BackupManager
            mgr = BackupManager()
            backups = mgr.list_backups()
            for b in backups:
                self.backup_list.insert(tk.END,
                    f"{b['filename']} ({b['size_mb']:.1f} MB) - {b['created'][:16]}")
        except Exception as e:
            logger.error("Error listing backups: %s", e)

    def _add_user(self):
        """Add new user dialog."""
        username = simpledialog.askstring("Add User", "Username:")
        if not username:
            return
        try:
            self.db.conn.execute(
                "INSERT INTO users (username, display_name, role) VALUES (?, ?, 'operator')",
                (username, username)
            )
            self.db.conn.commit()
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot add user: {e}")

    def _set_user_discount(self):
        """Set global discount for selected user."""
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a user first")
            return
        value = simpledialog.askfloat("Discount", "Global discount % for this user:", minvalue=0, maxvalue=100)
        if value is not None:
            uid = int(sel[0])
            self.db.conn.execute("UPDATE users SET discount_percent = ? WHERE id = ?", (value, uid))
            self.db.conn.commit()
            self.refresh()

    def _toggle_billing(self):
        """Toggle billing exclusion for selected user."""
        sel = self.users_tree.selection()
        if not sel:
            return
        uid = int(sel[0])
        self.db.conn.execute(
            "UPDATE users SET excluded_from_billing = 1 - excluded_from_billing WHERE id = ?", (uid,))
        self.db.conn.commit()
        self.refresh()

    def _add_microscope(self):
        """Register new microscope dialog."""
        name = simpledialog.askstring("Register Microscope", "Microscope name:")
        if not name:
            return
        serial = simpledialog.askstring("Register Microscope", "Serial number:")
        if not serial:
            return

        # Type selection
        type_win = tk.Toplevel(self)
        type_win.title("Select Type")
        type_win.geometry("300x100")
        ttk.Label(type_win, text="Microscope type (IMMUTABLE):").pack(pady=5)
        type_var = tk.StringVar(value="VEGA3")
        ttk.Radiobutton(type_win, text="VEGA3 (150 PLN/h)", variable=type_var, value="VEGA3").pack()
        ttk.Radiobutton(type_win, text="MIRA3_FEG (225 PLN/h)", variable=type_var, value="MIRA3_FEG").pack()

        def confirm():
            try:
                from repositories.repositories import AuditRepository, MicroscopeRepository
                from models.enums import MicroscopeType
                audit = AuditRepository(self.db)
                repo = MicroscopeRepository(self.db, audit)
                repo.create(name, serial, MicroscopeType(type_var.get()),
                           self.current_user_var.get() or "admin")
                self.refresh()
                type_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Cannot register: {e}")

        ttk.Button(type_win, text="Register", command=confirm).pack(pady=5)

    def _edit_rate(self):
        """Edit billing tier rate."""
        sel = self.rates_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a rate row first")
            return
        rate_id = int(sel[0])
        value = simpledialog.askfloat("Edit Rate", "New rate (PLN/h):", minvalue=0)
        if value is not None:
            self.db.conn.execute(
                "UPDATE billing_tiers SET rate_pln_per_hour = ? WHERE id = ?", (value, rate_id))
            self.db.conn.commit()
            self.refresh()

    def _backup_now(self):
        """Create manual backup."""
        from utils.backup import BackupManager
        mgr = BackupManager()
        path = mgr.create_backup(label="manual")
        self.backup_status.set(f"Backup created: {path}")
        self._load_backups()

    def _verify_integrity(self):
        """Run DB integrity check."""
        if not self.db:
            return
        result = self.db.verify_integrity()
        if result["integrity_ok"] and result["audit_coverage"]:
            self.backup_status.set("Integrity: OK | Audit coverage: OK")
        else:
            issues = "; ".join(result["issues"][:3])
            self.backup_status.set(f"ISSUES: {issues}")
