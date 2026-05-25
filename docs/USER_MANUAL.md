# TESCAN VEGA3 Log Analyzer - User Manual

## Overview

The TESCAN VEGA3 Log Analyzer is a desktop application for tracking and billing
microscope usage based on system log files. It parses history and HV data logs,
builds sessions, analyzes vacuum cycles, detects anomalies, and calculates costs.

---

## Tab 1: Dashboard

The Dashboard provides a quick overview of the system state.

### Statistics Cards (9 cards)
- Total Sessions - number of all imported sessions
- Total Billable Hours - sum of GVL open time across all sessions
- Total Cost (PLN) - sum of calculated costs
- Total Penalties (PLN) - sum of LEFT_VENTED penalties (100 PLN each)
- Imported Files - number of log files imported
- HV Samples - total high-voltage data points
- Vacuum Cycles - total pump cycles analyzed
- Anomalies - detected LONG_PUMP_TIME and IDLE_AFTER_READY events
- Active Users - distinct usernames found in sessions

### Import Files
- **Add Files...** - select one or more .log files to import
- **Scan Folder...** - recursively scan a folder for all .log files
- Files are auto-detected as HISTORY or HV type by filename pattern
- Duplicate files are skipped (SHA-256 hash check)

### Imported Files List
- Shows all imported files with type, date, and record count
- **REMOVE button** - deletes the file record AND all related data:
  sessions, vacuum cycles, HV samples, anomalies, penalties
- Delete key also triggers removal
- Confirmation dialog shows before deletion
- All removals are logged in the audit trail

### Recent Sessions
- Shows the 10 most recent sessions with user, time, duration, cost

---

## Tab 2: Sessions

Full list of all microscope user sessions with filtering and editing.

### Filters
- **User filter** - dropdown to show only one user's sessions
- **Status filter** - COMPLETE, NO_MEASUREMENT, PARTIAL, CANCELLED
- **Apply Filter** / **Clear** buttons

### Session Columns
- ID, User, Start Time, End Time, Duration, GVL Time, GVL Cycles,
  Status, Discount %, Cost (PLN)

### Right-Click Menu (PPM - Per-Session Actions)

Right-click any session row to access:

1. **Set Discount %** - reduces billable TIME (not rate). Range 0-100%.
   Session discount overrides user global discount.
2. **Set Fixed Cost (PLN)** - override calculated cost with a fixed amount.
3. **Set Manual Time (min)** - override GVL time with manual minutes.
4. **Exclude from Invoice (toggle)** - marks session as excluded, cost -> 0.
5. **Cancel Session** - sets status to CANCELLED, cost to 0.
6. **Show HV Chart** - switches to HV Charts tab with this session's time range.

Every PPM action writes an entry to the audit_log table with:
- action type, session ID, operator name, old value, new value, UTC timestamp.

---

## Tab 3: Vacuum

Displays vacuum system analysis results.

### Vacuum Cycles List
- Each pump cycle: PUMP start -> READY time -> end (GVL open or VENT/OFF)
- Statuses: OK, ABORTED, LEFT_VENTED, IN_PROGRESS
- Shows pump duration in seconds

### Penalties List
- LEFT_VENTED penalties (100 PLN each)
- Occurs when user vents chamber and turns off pump (VENT -> OFF)
- Shows user, timestamp, amount

### Anomalies List
- **LONG_PUMP_TIME** - pumping exceeds threshold (default 5 min)
  - warning: 5-10 min, critical: >10 min
  - Possible causes: sample contamination, outgassing, leak
- **IDLE_AFTER_READY** - long wait between vacuum ready and GVL open (default 30 min)
  - User may have left without working

### Summary Statistics
- Total cycles, OK count, aborted count, left vented count
- Total penalty amount, anomaly count

---

## Tab 4: Usage Heatmaps

Visual heatmaps showing microscope usage patterns over time.

### Heatmap Types
- **usage_time** - total GVL time per time slot (minutes)
- **pumping_time** - pump duration per time slot (minutes)
- **penalties** - penalty amounts per time slot (PLN)
- **idle_time** - idle after ready duration (minutes)
- **gvl_open_time** - GVL open duration for active sessions (minutes)

### Granularity
- **Hourly** - rows = days, columns = hours (0-23)
- **Daily** - rows = weeks, columns = weekdays (Mon-Sun)
- **Monthly** - rows = years, columns = months (Jan-Dec)

### Date Range
- Presets: 30 days, 90 days, 6 months, 1 year, All
- Any range can be selected - no restriction on date span

### Custom Color Scale
- Define 2 or more color points (value + color)
- Default: white (no data) -> green (low) -> red (high)
- Add intermediate points (e.g., yellow at 50%)
- Linear RGB interpolation between points
- Palette saved in settings (JSON format)
- Edit via "Edit Colors..." button

### Features
- Cell value annotations (toggle with "Show Values" checkbox)
- Export as PNG or SVG

---

## Tab 5: HV Charts

Interactive high-voltage data visualization for session analysis.

### Time Range
- Enter start/end timestamps manually, or
- Use "Show HV Chart" from Sessions tab PPM menu (auto-fills range)

### Parameters (checkboxes)
- HV [kV] - set high voltage
- Emission [uA] - beam emission current
- Filament [A] - emitter/filament current
- Chamber Pressure - specimen chamber vacuum level
- Gun Pressure - electron gun vacuum level
- GVL State - gun valve open/closed (step plot)
- Heating [%] - filament heating power

### Multiple Y Axes
- First parameter uses left Y axis
- Second parameter uses right Y axis
- Additional parameters create offset right axes

### Scale Options
- **Log Scale (Pressure)** - logarithmic Y for pressure parameters
- **Auto Scale Y** - automatic Y axis range fitting
- **Manual Y range** - set min/max values manually

### Pressure Units
- Pa (Pascal) - default, raw sensor data
- mbar (millibar) - 1 mbar = 100 Pa
- Torr - 1 Torr = 133.322 Pa

### Interaction
- **Zoom** - mouse scroll wheel (centered on cursor)
- **Box zoom** - use toolbar rectangle zoom tool
- **Pan** - use toolbar pan tool or drag
- **Horizontal scroll** - toolbar navigation
- **Crosshair** - shows time and value at cursor position

### Downsample
- For large datasets, reduce point density: 1x, 5x, 10x, 30x, 60x
- SQL-side filtering: only every Nth sample loaded
- Reduces rendering time for long recordings

### Export
- PNG (150 DPI) or SVG format

---

## Tab 6: Settings

Application configuration and user management.

### Billing Rate
- Flat rate in PLN per hour (default: 150.0)
- Applies to all new cost calculations
- Change requires "Save Rate" button

### Anomaly Thresholds
- **Long Pump Time** - seconds before flagging slow pump-down (default 300s = 5 min)
- **Idle After Ready** - seconds of idle before anomaly (default 1800s = 30 min)
- Changes apply to future imports only

### User Management
- **Add User** - create new user record (username + display name)
- **Edit Discount** - set user-level discount % (reduces billable time globally)
- **Toggle Excluded** - mark user as excluded from billing (cost always 0)
- User discount is overridden by session-level discount (PPM)

### Backup Controls
- **Create Backup Now** - manual database backup
- **Restore from File** - overwrite current DB with backup (confirmation required)
- **Auto-backup on start** - creates backup each time application launches
- Backups stored in backups/ folder with timestamp
- Old backups (>30 days) auto-cleaned, monthly snapshots kept

---

## Tab 7: Help

Displays this user manual in a scrollable text view.

---

## Key Concepts

### Billable Time Calculation
- Billable time = sum of all GVL open -> GVL close intervals in a session
- Multiple GVL cycles per session are summed
- Session without GVL open = NO_MEASUREMENT (0 cost)
- Cost = billable_hours * rate_pln_per_hour * (1 - discount/100)

### Session Statuses
- COMPLETE - normal session with start and end
- NO_MEASUREMENT - user logged in but never opened GVL (maintenance/check)
- PARTIAL - log file ends before session finished
- CANCELLED - manually cancelled via PPM menu

### Vacuum Cycle States
- PUMP -> READY = OK (normal pump-down)
- PUMP -> VENT = ABORTED (user cancelled)
- PUMP -> OFF = ABORTED (user cancelled)
- VENT -> OFF = LEFT_VENTED (penalty 100 PLN)

### Audit Trail
- Every data modification is recorded with:
  action, entity type, entity ID, operator, old/new values, UTC timestamp
- Enables full traceability of all billing changes

---

## File Formats

### History Logs (History-YYYY-MM.log)
- Event log with timestamps, parsed for sessions and vacuum events
- Auto-detected by filename containing "History" or "history"

### HV Data Logs (hv-YYYY-MM.log)
- Per-second high-voltage measurements (7 numeric columns + valve state)
- Auto-detected by filename containing "hv"

---

## Tips

- Import history files first, then HV files for the same period
- Use "Scan Folder" for bulk import of multiple months
- Check Vacuum tab after import for anomalies
- Use PPM menu to adjust billing before generating invoices
- Export heatmaps for monthly usage reports
- Create backups before major operations (restore available if needed)
