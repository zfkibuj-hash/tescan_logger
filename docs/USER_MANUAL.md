# TESCAN Log Analyzer — User Manual
## Version 2.0

---

## 1. Overview

TESCAN Log Analyzer is a desktop application for tracking and billing
microscope usage time based on system logs from TESCAN VEGA3 and MIRA3 FEG
electron microscopes.

The application is designed for GLP (Good Laboratory Practice) and
ISO 17025 compliance, ensuring data integrity and complete audit trails.

---

## 2. Getting Started

### First Launch
1. Run `TESCAN_Logger.exe` (or `python main.py` in dev mode)
2. Select your operator name from the login dropdown
3. Register your microscope(s) in Settings → Microscopes

### Registering a Microscope
- Go to **Settings** tab → Microscopes section
- Click "Add Microscope"
- Enter: Name, Serial Number, Type (VEGA3 or MIRA3 FEG)
- **Important:** The microscope type cannot be changed after registration
- Default billing rates are created automatically

---

## 3. Importing Logs

### From Dashboard tab:
1. Click "Add Files..." to select individual log files
2. Click "Scan Folder..." to import all logs from a directory
3. The system auto-detects file types (History / HV)
4. Already imported files are skipped (hash-based detection)

### Supported file patterns:
- History logs: `History-YYYY-MM.log`
- HV logs: `hv-YYYY-MM.log` or `hv-NAME-YYYY-MM.log`

### CLI import:
```
python main.py --import "C:\TESCAN\logs"
```

---

## 4. Tabs Reference

### Dashboard
- Summary statistics (total sessions, hours, costs)
- Recent sessions list
- File import controls
- Quick stats cards

### Sessions
- Full list of all parsed sessions
- Filters: by user, microscope, date range, status
- Right-click (PPM) menu for session operations:
  - Set discount %
  - Set fixed cost
  - Set manual time
  - Change billing tier
  - Change hourly rate
  - Exclude from invoice
  - Cancel session
  - View HV details

### Vacuum
- All vacuum pump/vent cycles
- Status indicators: OK, ABORTED, LEFT_VENTED
- Penalty list (100 PLN per LEFT_VENTED event)
- Pump time trends

### Heatmaps
- Visual time-usage heatmaps
- Types: usage, pumping, penalties, anomalies, idle, GVL
- Granularity: hourly, daily, monthly
- Custom date ranges (presets: 30d, 90d, 6m, 1y, all)
- Custom color scales (define your own gradient points)

### Session Analytics
- Per-session HV/emission charts (matplotlib)
- Parameters: HV, emission, filament, pressure, GVL state
- Zoom, pan, crosshair, export PNG/SVG
- Adjustable downsample factor

### Diagnostics
- Long-term trends (emission, pressure, vacuum)
- Anomaly detection results
- HV stability tracking
- Vacuum degradation monitoring

### Reports
- Generate billing reports (Excel / PDF / CSV)
- Monthly report template
- Audit trail export (PDF, GLP compliant)

### Settings
- User management (add, edit, set roles)
- Microscope management (register, set rates per tier)
- Billing tier configuration
- Backup management
- Data retention policy
- Application preferences

### Help
- This manual (rendered in-app)

---

## 5. Billing Model

### Rates
- Each microscope has rates configured per billing tier
- Default: VEGA3 = 150 PLN/h, MIRA3 FEG = 225 PLN/h

### Billing Tiers
| Tier | Description |
|------|-------------|
| PROJECT | Research projects (default) |
| UJ_UNIT | Jagiellonian University internal units |
| EXTERNAL | External entities |

### Discounts
- Discounts reduce billable TIME, not the hourly rate
- Can be set globally per user or per individual session
- Per-session discount overrides the user's global discount

### Penalties
- LEFT_VENTED event = 100 PLN penalty
- Applied when: VENT → OFF sequence detected

---

## 6. GLP / ISO Compliance

### Data Integrity
- Raw imported data cannot be deleted (only cancelled)
- Every modification creates an audit trail entry
- UTC timestamps on all audit records
- Version counter on modified entities

### Audit Trail
- Records: who, when, what was changed, old value, new value
- Exportable to PDF for auditors
- Integrity verification available (Tools → Verify)

### Operator Login
- Select operator at application start
- Optional PIN protection (configurable)
- All changes attributed to logged-in operator

---

## 7. Backup

- Automatic backup on every startup (configurable)
- Rolling retention: delete backups older than 30 days
- Monthly snapshots: kept indefinitely
- Manual backup: File → Backup Now

---

## 8. CLI Mode

```
python main.py --no-gui           # Start without GUI
python main.py --import DIR       # Import logs from directory
python main.py --backup           # Create manual backup
python main.py --verify           # Check database integrity
python main.py --debug            # Enable debug logging
```

---

## 9. Troubleshooting

| Problem | Solution |
|---------|----------|
| No files detected | Check filename pattern matches History-YYYY-MM.log |
| Wrong microscope detected | Verify log contains GVL (MIRA3) or HV ON (VEGA3) events |
| Import slow | Large HV files are normal; progress shown in status bar |
| Build fails | Ensure Python 3.12+ and all requirements.txt packages |
