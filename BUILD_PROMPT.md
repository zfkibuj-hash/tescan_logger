# TESCAN Log Analyzer — Master Build Prompt
# Wersja: 2.0 | Data: 2026-05
# Kompletny prompt do budowy aplikacji od zera.

---

## KONTEKST

Desktopowa aplikacja Windows do rozliczania czasu pracy mikroskopów
elektronowych TESCAN na podstawie logów systemowych.
Zgodna z zasadami GLP/ISO 17025 (integralność danych, audit trail, niezmienność danych surowych).

---

## OBSŁUGIWANE MIKROSKOPY

| Mikroskop | Typ | Stawka domyślna | Opis |
|-----------|-----|-----------------|------|
| TESCAN VEGA3 | LaB6 filament | 150 PLN/h | Filament termojonowy |
| TESCAN MIRA3 FEG | Field Emission Gun | 225 PLN/h | Emisja polowa (FEG) |

- Typ mikroskopu przypisany na sztywno do numeru seryjnego — niezmienialny po rejestracji.
- Stawki konfigurowane per mikroskop per billing_tier w Settings.

---

## PLIKI LOGÓW — TYPY I FORMATY

### 1. History-YYYY-MM.log — logi zdarzeń sesji i vacuum

Format: `YYYY-MM-DD HH:MM:SS.fff [I] treść zdarzenia`

Kluczowe zdarzenia:
```
== Session started for user: USERNAME ==
== Session finished ==
HV: HV has been turned ON
HV: HV has been turned OFF
HV: HV heating has been turned OFF     ← FILAMENT_OFF (VEGA3)
Vacuum: command GVL open, ...          ← Gun Valve (MIRA3 FEG)
Vacuum: command GVL close, ...
Vacuum: command PUMP, ...
Vacuum: command VENT, ...
Vacuum: command OFF, ...
Vacuum: Vacuum: ready in 102 s, ...
== Starting software ==
== Terminating software ==
```

Auto-detekcja mikroskopu z History:
- obecność `GVL open` / `GVL close` → MIRA3_FEG
- obecność `HV has been turned ON`, brak GVL → VEGA3

### 2. hv-YYYY-MM.log — logi HV/emisja (1 próbka/sekundę)

**VEGA3** (8 kolumn + stan valve):
```
YYYY-MM-DD HH:MM:SS.fff [I]  set_hv  actual_hv  emission_uA  emitter_A  heating%  gun_p  chamber_p  Open/Closed
```

Kolumny VEGA3:
1. set_hv_kV
2. actual_hv_kV
3. emission_current_uA
4. emitter_current_A (filament heating)
5. heating_percent
6. gun_pressure_Pa
7. chamber_pressure_Pa
8. gun_valve_state: Open / Closed

**MIRA3 FEG** (11 kolumn, bez stanu valve):
```
YYYY-MM-DD HH:MM:SS.fff [I]  set_hv  extractor_kV  suppressor_V  current_uA  emission_uA  filament_A  0xFLAGS  gun_ion_p  actual_hv  col_ion_p  chamber_p
```

Kolumny MIRA3 FEG:
1. set_hv_kV
2. extractor_voltage_kV
3. suppressor_voltage_V
4. total_current_uA
5. emission_current_uA
6. filament_current_A
7. flags_hex (np. 0x2000)
8. gun_ion_pump_pressure_Pa
9. actual_hv_kV
10. column_ion_pump_pressure_Pa
11. chamber_pressure_Pa

Auto-detekcja HV: skanuj pierwsze 50 linii danych:
- 8 numerycznych + słowo (Open/Closed) → VEGA3
- 11 numerycznych/hex → MIRA3_FEG

---

## ZASADY BIZNESOWE — KRYTYCZNE

### Czas pracy mikroskopu

**VEGA3:**
- Czas pracy = `HV has been turned ON` → `HV has been turned OFF`

**MIRA3 FEG:**
- Czas pracy = `GVL open` → `GVL close`
- HV na MIRA pozostaje włączone między sesjami — NIE liczyć jako czas pracy

### Gwarancja sprzętowa — brak sesji łączonych

**KRYTYCZNA ZASADA:** Przelogowanie w trakcie aktywnego użycia jest NIEMOŻLIWE sprzętowo:
- MIRA3 FEG: GVL jest ZAWSZE zamykany przed wylogowaniem
- VEGA3: HV jest ZAWSZE wyłączane przed wylogowaniem

**Konsekwencja:** Każdy przedział GVL/HV należy do dokładnie jednego użytkownika.
NIE implementować mechanizmu ręcznego podziału sesji (MANUAL_SPLIT).

### Ciągłość między miesiącami

Sesja zaczynająca się 31-go o 23:50 i kończąca 1-go o 00:10 jest w DWÓCH plikach.
- `PARTIAL_SESSION` z końca pliku łączy się z `INCOMPLETE_CONTEXT` z początku następnego
- Matching: ten sam username + timestamp gap < 5 min
- Wynikowa sesja: status COMPLETE, czas = suma obu części

### Statusy sesji (tylko te cztery):
- `COMPLETE` — normalna sesja z początkiem i końcem
- `PARTIAL_SESSION` — log ucięty, brak końca (GVL/HV otwarte na końcu pliku)
- `INCOMPLETE_CONTEXT` — brak początku (log zaczyna się w środku sesji)
- `CANCELLED` — anulowana ręcznie przez operatora

### Vacuum — statusy cykli
```
PUMP → READY    = OK
PUMP → VENT     = ABORTED
PUMP → OFF      = ABORTED
VENT → OFF      = LEFT_VENTED → kara 100 PLN
```

### Rozliczenia — model cennikowy

**Stawki domyślne per mikroskop:**
- VEGA3: 150 PLN/h
- MIRA3 FEG: 225 PLN/h

**Trzy pozycje cennikowe (billing_tier):**

| Tier | Opis |
|------|------|
| `PROJECT` | Projekty badawcze (domyślny) |
| `UJ_UNIT` | Jednostki Uniwersytetu Jagiellońskiego |
| `EXTERNAL` | Jednostki zewnętrzne |

Każdy tier ma osobną stawkę PLN/h konfigurowaną per mikroskop w Settings.

**Rabat:**
- Rabat zmniejsza rozliczany CZAS, nie stawkę godzinową
- Per użytkownik (globalnie) lub per sesja (PPM menu)
- Per-sesja nadpisuje globalny

**Ręczna edycja sesji (PPM):**
- Override kosztu (kwota PLN na sztywno)
- Override czasu (minuty na sztywno)
- Rabat % per sesja
- Zmiana billing_tier
- Zmiana stawki godzinowej per sesja
- Anulowanie sesji
- Wykluczenie z faktury

**Kary:**
- LEFT_VENTED: 100 PLN za każdy przypadek

**Konta specjalne:**
- `excluded_from_billing=True` → brak kosztów, vacuum nadal analizowane

---

## GLP / ISO 17025 — COMPLIANCE FEATURES

| Feature | Implementacja |
|---------|---------------|
| Niezmienność danych surowych | Sesje/pomiary nie mogą być USUNIĘTE — tylko cancelled z audit trail |
| Audit trail | KAŻDA zmiana danych → wpis w audit_log (kto, kiedy, co, przed, po) |
| Logowanie operatora | Przy starcie: wybierz kto pracuje (dropdown). Opcja: wymagaj PIN |
| Timestamping | Audit log w UTC |
| Versioning | Jawny version counter na edytowanych rekordach |
| Data integrity check | Przycisk "Verify DB integrity" — sprawdza spójność audit_log |
| Data retention | Konfigurowane: "dane min. X lat" — blokuje usuwanie |
| Export audit trail | Osobny raport PDF dla audytora |
| Podpis operatora | Przy override/cancel — zapis kto zatwierdził |

---

## TECHNOLOGIE

- Python 3.12
- **GUI:** tkinter + ttk (NIE customtkinter)
- **DB:** sqlite3 (WAL mode, thread-local connections)
- **Excel:** openpyxl
- **PDF:** reportlab
- **Wykresy:** matplotlib embedded w tkinter (TkAgg backend)
- **Liczby:** numpy
- **Build:** PyInstaller --onedir (szybszy start niż --onefile, mniej awaryjny)

**Uwaga build:** `--onedir` tworzy folder z EXE + DLL. Można zipnąć i dystrybuować.
Szybszy start, mniejsze ryzyko false-positive antywirusów, łatwiejszy debug.

---

## ARCHITEKTURA

```
Strategy Pattern  — parsery plików (History vs HV)
Factory Pattern   — tworzenie parserów na podstawie wykrytego formatu
Repository Pattern — warstwa dostępu do bazy danych
Service Layer     — logika biznesowa oddzielona od GUI
Observer Pattern  — GUI reaguje na zmiany danych (callbacks)
```

---

## STRUKTURA PROJEKTU

```
tescan_logger/
├── main.py                    # entry point, logging setup
├── build.bat                  # PyInstaller --onedir build
├── run_dev.bat                # dev runner
├── requirements.txt
├── README.md
│
├── config/
│   └── config.json.example
│
├── models/
│   ├── __init__.py
│   ├── enums.py               # MicroscopeType, EventType, SessionStatus, AuditAction...
│   ├── dataclasses.py         # Session, VacuumCycle, User, Microscope, Anomaly, Penalty...
│   └── hv_models.py           # HVSample, HVSessionStats, PressureEvent
│
├── database/
│   ├── __init__.py
│   └── db_manager.py          # schema, WAL, thread-local conn, migrations
│
├── parser/
│   ├── __init__.py
│   ├── log_parser.py          # History log regex parser
│   ├── hv_parser.py           # HV log parser, auto-detect, generator
│   └── file_registry.py       # file type detection, include/exclude patterns
│
├── services/
│   ├── __init__.py
│   ├── import_service.py      # pipeline: scan → parse → build → persist
│   ├── session_builder.py     # ParsedEvents → Sessions + cross-month continuity
│   ├── vacuum_analyzer.py     # VacuumCycles + Penalties + Anomalies
│   └── billing_service.py     # cost calculation, discounts, tiers
│
├── repositories/
│   ├── __init__.py
│   ├── repositories.py        # Session, Vacuum, User, Microscope, Anomaly, Audit repos
│   └── hv_repository.py       # HVSample repo, batch insert
│
├── analytics/
│   ├── __init__.py
│   ├── hv_analytics.py        # emission drift, pressure spikes, diagnostics
│   └── heatmap_engine.py      # heatmap data matrices, custom color scales
│
├── exporters/
│   ├── __init__.py
│   └── exporters.py           # Excel, PDF, CSV, audit trail PDF
│
├── utils/
│   ├── __init__.py
│   └── backup.py              # rolling backup + monthly snapshots
│
├── gui/                       # (osobna faza budowy)
│   └── ...
│
├── docs/
│   └── USER_MANUAL.md         # instrukcja obsługi (renderowana w Help)
│
├── sample_logs/
│   ├── vega3_history.log
│   ├── mira3_history.log
│   ├── vega3_hv.log
│   └── mira3_hv.log
│
├── exports/                   # generowane raporty
├── backups/                   # backupy bazy
└── logs/                      # logi aplikacji
```

---

## SCHEMAT BAZY DANYCH

```sql
-- Core tables
microscopes          -- serial, type (immutable), name, location, active
users                -- username, display_name, role, discount%, excluded_from_billing, pin_hash
billing_tiers        -- microscope_id, tier_name, rate_pln_per_hour

-- Session data
sessions             -- start/end, user, microscope, status, billing_tier, cost fields, version
vacuum_cycles        -- pump/vent/off cycles with status and ready_time
penalties            -- LEFT_VENTED penalties (100 PLN each)

-- HV data (separate DB: tescan_hv.db)
hv_samples           -- timestamp, microscope_id, all columns per type

-- Analysis
anomalies            -- detected anomalies (pressure, emission, vacuum)
pressure_events      -- detected pressure spikes from HV analysis

-- System
settings             -- key-value (rates, folders, retention policy)
file_cache           -- file hash for incremental import
parser_errors        -- parse errors with context
audit_log            -- EVERY data modification (action, entity, old/new JSON, UTC timestamp)
```

**HV data w osobnej bazie** (`tescan_hv.db`) — miliony wierszy nie spowalniają głównej bazy.

Indeksy: timestamp, microscope_id, username, session_id, billing_tier

---

## AUDIT TRAIL

Każda operacja modyfikująca dane → wpis w audit_log:
- action: CREATE/EDIT/CANCEL/OVERRIDE_COST/OVERRIDE_TIME/CHANGE_TIER/IMPORT/EXPORT/BACKUP/SETTINGS_CHANGE
- entity_type + entity_id
- changed_by (current operator)
- old_value, new_value (JSON)
- created_at (UTC, auto)
- version (incrementing per entity)

---

## IMPORT PLIKÓW

- **Add Files…** — wybór pojedynczych plików
- **Scan Folder…** — rekurencyjnie z filtrami include/exclude
- Include pattern: `History-\d{4}-\d{2}\.log$` (domyślne)
- HV pattern: `hv[-_].*\d{4}-\d{2}.*\.log$`
- Toggles: History ON/OFF, HV ON/OFF
- File type auto-detection (badge HISTORY / HV)
- Incremental: skip already imported files (file_cache hash check)
- Walidacja: monotoniczność timestampów, wykrywanie dziur >1h w HV

---

## SESJA — PPM MENU

| Akcja | Efekt |
|-------|-------|
| Ustaw rabat % | Zmniejsza czas, przelicza koszt |
| Ustaw kwotę na sztywno | cost_override PLN |
| Wpisz czas ręcznie | time_override (minuty) |
| Zmień tier | PROJECT / UJ_UNIT / EXTERNAL |
| Zmień stawkę PLN/h | rate_override per sesja |
| Wyklucz z faktury | toggle excluded_from_invoice |
| Anuluj sesję | cancelled=True, cost=0 |
| Pokaż HV | otwórz Session Analytics |
| Pokaż w logu | podgląd pliku źródłowego |

Każda operacja → audit_log + version increment.

---

## HEATMAPY

- 6 typów: usage_time, pumping_time, penalties, vacuum_anomalies, idle_time, gvl_open_time
- Granulacja: hourly / daily / monthly
- **Zakres dat: DOWOLNY** (presety: 30d / 90d / 6m / 1y / All)
- Filtry: mikroskop, użytkownik
- **Custom skala kolorów:**
  - ≥2 punkty (wartość + kolor)
  - Domyślnie: brak=biały, 0=zielony, max=czerwony
  - Użytkownik dodaje punkty pośrednie (np. żółty na 50%)
  - Interpolacja liniowa RGB
  - Zapis palety w settings (JSON)
- Annotacje wartości w komórkach (toggle)
- Export PNG / SVG

---

## WYKRESY (matplotlib TkAgg)

Session Analytics — multi-panel (sharex):
- HV [kV], Emission [µA], Filament [A]
- Chamber pressure [Pa] (log), Gun pressure [Pa] (log)
- GVL state (step plot, jeśli dostępne)
- Downsample: 1x / 5x / 10x / 30x / 60x

Diagnostics — trendy długoterminowe:
- Emission trend + rolling avg + trend line
- Pressure trend (rolling median)
- Vacuum degradation (pump ready times)
- HV stability (actual vs set)

ChartWidget: zoom, pan, crosshair, export PNG/SVG

---

## WYDAJNOŚĆ

- HV: zawsze importuj 1x (pełna rozdzielczość), downsample przy wyświetlaniu (SQL-side)
- Batch insert: generator + executemany (1000 rows/batch)
- HV w osobnej bazie (tescan_hv.db)
- WAL mode + PRAGMA synchronous=NORMAL
- Indeksy na timestamp, microscope_id

---

## BACKUP

- Auto-backup przy starcie (konfigurowalne)
- Rolling: usuwaj starsze niż N dni (domyślnie 30)
- Monthly snapshot: `tescan_monthly_YYYY-MM.db`
- Ręczny backup z Settings

---

## LOGOWANIE OPERATORA

- Przy starcie: dropdown z listą użytkowników
- Opcjonalnie: PIN (4-6 cyfr, hash w DB)
- current_user → każdy audit_log entry
- Brak logowania = brak dostępu do edycji (tylko podgląd)

---

## ZAKŁADKI GUI (9 zakładek)

1. 📊 Dashboard — statystyki, import plików, ostatnie sesje
2. 📋 Sessions — tabela, filtry, PPM menu, export
3. 🔬 Vacuum — cykle, statusy, trendy, kary
4. 🗓 Heatmaps — heatmapy z custom kolorami
5. 📈 Session Analytics — wykresy HV/emission per sesja
6. 🔭 Diagnostics — trendy + anomalie + alerty
7. 📄 Reports — generowanie Excel/PDF/CSV + audit trail
8. ⚙ Settings — użytkownicy, mikroskopy, stawki, backup, retention
9. ❓ Help — wbudowany manual (USER_MANUAL.md)

---

## BUILD

- `build.bat` → PyInstaller `--onedir --windowed`
- Wynik: folder `dist/tescan_logger/` z EXE + zależności
- Dystrybucja: zipnij folder → gotowe
- `run_dev.bat` → uruchomienie z venv w trybie dev

---

## RAPORT MIESIĘCZNY

- Auto-propozycja na koniec miesiąca
- Szablon: sesje per user, sumy kosztów, kary, anomalie
- Podpis generującego (GLP)
- Export Excel + PDF

---

## WALIDACJA PRZY IMPORCIE

- Monotoniczność timestampów (rosnące)
- Duplikaty (file_cache hash)
- Dziury w HV logu (>1h przerwa = warning)
- Raport błędów parsera (parser_errors table + Error panel w Diagnostics)

---

## DODATKOWE ZASADY

- Brak customtkinter — tylko tkinter + ttk
- Brak manual split — hardware gwarantuje
- Brak drag & drop (tkinterdnd2) — Add Files + Scan Folder wystarczą
- Audit trail na KAŻDEJ modyfikacji danych
- Dane surowe NIEUSUWALNE (GLP)
- Komentarze w kodzie: angielski (spójnie)
- Moduły <500 linii
- Obsługa wyjątków wszędzie (DB, IO, parse)
- Aplikacja w pełni offline
