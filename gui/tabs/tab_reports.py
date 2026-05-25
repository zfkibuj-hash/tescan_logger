"""Reports tab - generate Excel, PDF, CSV billing reports."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ReportsTab(ttk.Frame):
    """Report generation: Excel, PDF, CSV, Audit Trail."""

    def __init__(self, parent, db_manager=None, current_user_var=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db_manager
        self.current_user_var = current_user_var or tk.StringVar(value="admin")
        self._build_ui()

    def _build_ui(self):
        """Build reports tab."""
        ttk.Label(self, text="Report Generation", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 5))

        # Report type selection
        type_frame = ttk.LabelFrame(self, text="Report Type", padding=10)
        type_frame.pack(fill=tk.X, padx=10, pady=5)

        self.report_type = tk.StringVar(value="billing_excel")
        reports = [
            ("Billing Report (Excel)", "billing_excel"),
            ("Billing Report (PDF)", "billing_pdf"),
            ("Sessions Export (CSV)", "sessions_csv"),
            ("Vacuum Cycles (CSV)", "vacuum_csv"),
            ("Audit Trail (PDF)", "audit_pdf"),
        ]
        for text, value in reports:
            ttk.Radiobutton(type_frame, text=text, variable=self.report_type, value=value).pack(anchor="w")

        # Options
        opts_frame = ttk.LabelFrame(self, text="Options", padding=10)
        opts_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(opts_frame, text="Report title:").grid(row=0, column=0, sticky="w")
        self.title_entry = ttk.Entry(opts_frame, width=40)
        self.title_entry.insert(0, f"TESCAN Billing Report - {datetime.now().strftime('%Y-%m')}")
        self.title_entry.grid(row=0, column=1, padx=5, sticky="ew")

        # Generate button
        ttk.Button(self, text="Generate Report...", command=self._generate,
                   style="Accent.TButton").pack(pady=15)

        # Status
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, font=("Segoe UI", 9)).pack(anchor="w", padx=10)

    def _generate(self):
        """Generate selected report."""
        rtype = self.report_type.get()

        ext_map = {
            "billing_excel": ("Excel files", "*.xlsx"),
            "billing_pdf": ("PDF files", "*.pdf"),
            "sessions_csv": ("CSV files", "*.csv"),
            "vacuum_csv": ("CSV files", "*.csv"),
            "audit_pdf": ("PDF files", "*.pdf"),
        }
        ft = ext_map.get(rtype, ("All", "*.*"))
        default_ext = ft[1].replace("*", "")

        path = filedialog.asksaveasfilename(
            defaultextension=default_ext,
            filetypes=[ft],
            initialfile=f"tescan_report_{datetime.now().strftime('%Y%m%d')}{default_ext}"
        )
        if not path:
            return

        try:
            if rtype == "billing_excel":
                self._gen_billing_excel(path)
            elif rtype == "billing_pdf":
                self._gen_billing_pdf(path)
            elif rtype == "sessions_csv":
                self._gen_sessions_csv(path)
            elif rtype == "vacuum_csv":
                self._gen_vacuum_csv(path)
            elif rtype == "audit_pdf":
                self._gen_audit_pdf(path)

            self.status_var.set(f"Report saved: {path}")
            messagebox.showinfo("Done", f"Report generated:\n{path}")

        except ImportError as e:
            messagebox.showerror("Missing Package", f"Install required package: {e}")
        except Exception as e:
            self.status_var.set(f"Error: {e}")
            messagebox.showerror("Error", f"Report generation failed:\n{e}")

    def _gen_billing_excel(self, path):
        from exporters.exporters import ExcelExporter
        from repositories.repositories import AuditRepository, SessionRepository
        audit = AuditRepository(self.db)
        repo = SessionRepository(self.db, audit)
        sessions = repo.get_all(limit=5000)
        penalties = self.db.conn.execute("SELECT * FROM penalties").fetchall()
        # Convert penalty rows to Penalty objects
        from models.dataclasses import Penalty
        pen_list = [Penalty(
            id=p["id"], username=p["username"], amount=p["amount"],
            reason=p["reason"]
        ) for p in penalties]
        ExcelExporter.export_billing_report(
            sessions, pen_list, path,
            report_title=self.title_entry.get(),
            generated_by=self.current_user_var.get()
        )

    def _gen_billing_pdf(self, path):
        from exporters.exporters import PDFExporter
        from repositories.repositories import AuditRepository, SessionRepository
        audit = AuditRepository(self.db)
        repo = SessionRepository(self.db, audit)
        sessions = repo.get_all(limit=5000)
        from models.dataclasses import Penalty
        penalties = self.db.conn.execute("SELECT * FROM penalties").fetchall()
        pen_list = [Penalty(
            id=p["id"], username=p["username"], amount=p["amount"],
            reason=p["reason"]
        ) for p in penalties]
        PDFExporter.export_billing_report(
            sessions, pen_list, path,
            report_title=self.title_entry.get(),
            generated_by=self.current_user_var.get()
        )

    def _gen_sessions_csv(self, path):
        from exporters.exporters import CSVExporter
        from repositories.repositories import AuditRepository, SessionRepository
        audit = AuditRepository(self.db)
        repo = SessionRepository(self.db, audit)
        sessions = repo.get_all(limit=10000)
        CSVExporter.export_sessions(sessions, path)

    def _gen_vacuum_csv(self, path):
        from exporters.exporters import CSVExporter
        from repositories.repositories import VacuumRepository
        repo = VacuumRepository(self.db)
        cycles = repo.get_cycles(limit=10000)
        CSVExporter.export_vacuum(cycles, path)

    def _gen_audit_pdf(self, path):
        from exporters.exporters import PDFExporter
        from repositories.repositories import AuditRepository
        audit_repo = AuditRepository(self.db)
        entries = audit_repo.get_all(limit=5000)
        PDFExporter.export_audit_trail(
            entries, path,
            generated_by=self.current_user_var.get()
        )
