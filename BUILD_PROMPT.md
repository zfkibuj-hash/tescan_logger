# TESCAN VEGA3 Log Analyzer - Build Prompt
# Wersja: 3.0 | Data: 2026-05
# Czysty start. Uzyj tego promptu zeby zbudowac aplikacje od zera.

---

## KONTEKST

Desktopowa aplikacja Windows do rozliczania czasu pracy mikroskopu
elektronowego TESCAN VEGA3 (LaB6) na podstawie logow systemowych.
Na razie obslugujemy TYLKO Vege3.

---

## MIKROSKOP

- **TESCAN VEGA3** - filament LaB6
- Stawka domyslna: konfigurowana w Settings (np. 150 PLN/h)
- Flat rate - jedna stawka, bez tierow
- Numer seryjny: zaczyna sie od VG (np. VG11841379PL)

---

## PLIKI LOGOW - FORMATY

### 1. History-YYYY-MM.log - logi zdarzen

Format linii: `YYYY-MM-DD HH:MM:SS.fff [I] tresc zdarzenia`
Linie z `[E]` to bledy (selftest, TMP expired) - parsowac tez.

Kluczowe zdarzenia (regex):
```
== Session started for user: USERNAME ==
== Session finished ==
HV: HV has been turned ON
HV: HV has been turned OFF
HV: HV heating has been turned OFF
Vacuum: command GVL open, ...
Vacuum: command GVL close, ...
Vacuum: command PUMP, ...
Vacuum: command VENT, ...
Vacuum: command OFF, ...
Vacuum: Vacuum: ready in NNN s, ...
== Starting software ==
== Terminating software ==
SN: VG...                              <- numer seryjny
```

Dodatkowe zdarzenia do parsowania (informacyjne):
```
HV: HV is being turned ON             <- poczatek procesu wlaczania (nie = wlaczone!)
HV: HV is being turned OFF            <- poczatek wylaczania
HV: Filament time: NNN h NN min, type: LaB6
Vacuum: Vacuum time: NNN h NN min
ChamberView: starting live image       <- podglad komory
[E] ...                                <- bledy (osobna kategoria)
```

### 2. hv-YYYY-MM.log - dane HV/emisja (1 probka/sekunde)

Format VEGA3 (7 kolumn numerycznych + stan zaworu):
```
YYYY-MM-DD HH:MM:SS.fff [I]  set_hv  actual_hv  emission_uA  emitter_A  heating%  gun_p  chamber_p  Open/Closed
```

Przyklad:
```
2026-05-05 15:51:27.416 [I]  30.0  30.0  0.5  2.794  41.4  5.4e-005  7.6e-003  Open
```

Kolumny:
1. set_hv_kV (zadane napiecie)
2. actual_hv_kV (zmierzone napiecie)
3. emission_current_uA (prad emisji wiazki)
4. emitter_current_A (prad grzania filamentu)
5. heating_percent (% mocy grzania)
6. gun_pressure_Pa (cisnienie w dziale)
7. chamber_pressure_Pa (cisnienie w komorze)
8. gun_valve_state: "Open" / "Closed" (stan GVL)

Detekcja formatu: ostatnie pole to slowo Open/Closed, reszta numeryczna.

---

## ZASADY BIZNESOWE - KRYTYCZNE

### Czas pracy mikroskopu (BILLABLE TIME)

**VEGA3: Czas pracy = GVL open -> GVL close**

Sekwencja normalna:
```
PUMP -> READY -> HV ON -> GVL open -> [PRACA] -> GVL close -> HV OFF
```

- GVL jest ZAWSZE zamykany przed wylogowaniem (gwarancja sprzetowa)
- HV jest ZAWSZE wylaczane przed wylogowaniem
- W jednej sesji moze byc WIELE cykli GVL open/close - SUMUJEMY czas
- Sesja BEZ GVL open = sesja bez pomiaru (maintenance/check) - 0 min billable

### NIE IMPLEMENTOWAC:
- Manual split sesji (sprzet to gwarantuje)
- Laczenia sesji miedzy plikami (na razie nie potrzebne)

### Statusy sesji:
- `COMPLETE` - sesja z poczatkiem i koncem
- `NO_MEASUREMENT` - sesja bez GVL (user wszedl, sprawdzil cos, wyszedl)
- `PARTIAL` - log uciety, brak session finished
- `CANCELLED` - anulowana recznie

### Vacuum - statusy cykli:
```
PUMP -> READY    = OK
PUMP -> VENT     = ABORTED
PUMP -> OFF      = ABORTED
VENT -> OFF      = LEFT_VENTED -> kara 100 PLN
```

### Detekcja anomalii:
1. **LONG_PUMP_TIME** - pompowanie trwa > prog (domyslnie 5 min)
   Przyczyna: kontaminacja probki, outgassing, nieszczelnosc
   Severity: warning <10 min, critical >=10 min

2. **IDLE_AFTER_READY** - dlugie czekanie READY -> GVL open (domyslnie > 30 min)
   Przyczyna: user poszedl na obiad, zapominal
   Przyklad: PUMP 9:00, READY 9:05, GVL open 14:00 = idle 4h 55min

### Rozliczenia:
- Flat rate: jedna stawka PLN/h (konfigurowana w Settings)
- Rabat procentowy: zmniejsza rozliczany CZAS, nie stawke
- Rabat godzinowy: odejmuje konkretna liczbe godzin od rozliczenia
  (np. bylo 12h, odejmujemy 2h, rozliczamy 10h - oryginalna wartosc zachowana)
- Rabat per user (globalny) lub per sesja (PPM)
- Per-sesja nadpisuje globalny
- Override kosztu (kwota na sztywno)
- Override czasu (minuty na sztywno)
- `excluded_from_billing` = konto bez kosztow (vacuum nadal analizowane)
- Kara LEFT_VENTED: 100 PLN za kazdy przypadek

Priorytet kalkulacji:
1. excluded -> 0 PLN
2. override_cost -> uzywamy kwoty na sztywno
3. override_time_minutes -> rate * czas_reczny
4. gvl_total * (1 - discount%) - discount_hours*3600 = billable_seconds

### Usuwanie wczytanych plikow:
- Mozliwosc usuniecia zaimportowanego pliku z bazy
- Usuwane sa WSZYSTKIE dane powiazane z tym plikiem (sesje, vacuum, HV)
- Audit log zapisuje kto i kiedy usunol
- Uzyteczne gdy niechcacy wczytamy plik 2 razy lub zly plik

---

## WYKRESY HV (matplotlib TkAgg) - KRYTYCZNE

Wykres danych z hv-YYYY-MM.log w kontekscie sesji uzytkownika:

### Funkcjonalnosc:
- **Zoom** (scroll myszy + box select)
- **Pan** (przeciaganie)
- **Scroll** horyzontalny (przesuwanie osi czasu)
- **Skala na sztywno** - uzytkownik moze ustalic zakres osi Y recznie
- **Skala automatyczna** - dopasowanie do danych
- **Skala logarytmiczna** - przelacznik log/lin dla cisnienia
- **Zmiana jednostek cisnienia** - Pa / mbar / Torr (przelicznik)
- **Wiele osi Y** - rozne jednostki na osobnych osiach (lewa/prawa/dodatkowe)
- **Tryby prezentacji:**
  - Linia ciagla
  - Punkty (scatter)
  - Step plot (dla GVL state)
- **Export** PNG / SVG
- **Crosshair** (linie sledzace kursor z wartosciami)

### Parametry do wyboru (checkboxy, kazdy na osobnej osi Y):
- HV [kV] - lewa os
- Emission current [uA] - prawa os
- Emitter/filament current [A]
- Chamber pressure [Pa/mbar/Torr] - skala log
- Gun pressure [Pa/mbar/Torr] - skala log
- GVL state (Open/Closed) - step plot, binarne
- Heating [%]

### Downsample dla duzych danych:
- SQL-side: `WHERE (rowid % N) = 0`
- Uzytkownik wybiera: 1x / 5x / 10x / 30x / 60x
- Auto-downsample na podstawie ilosci probek w zakresie

---

## HEATMAPY (Usage Heatmaps)

- Typy: usage_time, pumping_time, penalties, idle_time, gvl_open_time
- Granulacja: hourly / daily / monthly
- **Zakres dat: DOWOLNY** (presety: 30d / 90d / 6m / 1y / All)
- Filtry: uzytkownik
- **Custom skala kolorow:**
  - Uzytkownik definiuje >=2 punkty (wartosc + kolor)
  - Domyslnie: brak danych = bialy, 0 = zielony, max = czerwony
  - Mozliwosc dodania punktow posrednich (np. zolty na 50%)
  - Interpolacja liniowa RGB
  - Zapis palety w settings (JSON)
- Annotacje wartosci w komorkach (toggle)
- Export PNG / SVG

---

## TECHNOLOGIE

- Python 3.12
- **GUI:** tkinter + ttk (NIE customtkinter)
- **DB:** sqlite3 (WAL mode)
- **Excel:** openpyxl
- **PDF:** reportlab
- **Wykresy:** matplotlib embedded (TkAgg backend)
- **Build:** PyInstaller --onedir --windowed

---

## ARCHITEKTURA

```
Repository Pattern - warstwa dostepu do DB
Service Layer     - logika biznesowa oddzielona od GUI
```

Proste, czytelne, bez overengineeringu.

---

## STRUKTURA PROJEKTU

```
tescan_logger/
├── main.py                    # entry point
├── build.bat                  # PyInstaller --onedir
├── run_dev.bat                # dev runner
├── requirements.txt
├── BUILD_PROMPT.md            # ten plik
│
├── config/
│   └── config.json.example
│
├── models/
│   ├── __init__.py
│   ├── enums.py               # EventType, SessionStatus, VacuumStatus, AnomalyType
│   └── dataclasses.py         # Session, VacuumCycle, HVSample, User, Penalty, Anomaly
│
├── database/
│   ├── __init__.py
│   └── db_manager.py          # schema, WAL, init, migrations
│
├── parser/
│   ├── __init__.py
│   ├── log_parser.py          # History log parser (regex)
│   └── hv_parser.py           # HV log parser (1/s data)
│
├── services/
│   ├── __init__.py
│   ├── import_service.py      # import pipeline + usuwanie plikow
│   ├── session_builder.py     # events -> sessions (sumuje GVL cycles)
│   ├── vacuum_analyzer.py     # vacuum cycles + penalties + anomalie
│   └── billing_service.py     # flat rate + rabaty + override
│
├── repositories/
│   ├── __init__.py
│   └── repositories.py        # Session, Vacuum, User, HV, Audit repos
│
├── exporters/
│   ├── __init__.py
│   └── exporters.py           # Excel, PDF, CSV
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py         # glowne okno + 7 zakladek
│   └── tabs/
│       ├── __init__.py
│       ├── tab_dashboard.py   # statystyki + import + usuwanie plikow
│       ├── tab_sessions.py    # lista sesji + PPM menu
│       ├── tab_vacuum.py      # cykle + kary + anomalie
│       ├── tab_heatmaps.py    # Usage Heatmaps z custom kolorami
│       ├── tab_hv_charts.py   # wykresy HV z multi-axis + zoom/pan
│       ├── tab_settings.py    # stawka, uzytkownicy, backup
│       └── tab_help.py        # manual
│
├── docs/
│   └── USER_MANUAL.md
│
└── sample_logs/
    ├── vega3_history.log
    └── vega3_hv.log
```

---

## SCHEMAT BAZY DANYCH

```sql
users            -- username, display_name, discount%, excluded_from_billing, pin_hash
sessions         -- start/end, user, duration_seconds, gvl_total_seconds, cost, status, overrides
vacuum_cycles    -- PUMP/VENT/OFF cycles + status + ready_time
penalties        -- LEFT_VENTED (100 PLN each)
anomalies        -- LONG_PUMP_TIME, IDLE_AFTER_READY
hv_samples       -- per-second HV data (osobna tabela, duzo danych)
settings         -- key-value (stawka, progi anomalii, kolory heatmapy)
file_cache       -- zaimportowane pliki (path, hash, type, date, record_count)
parser_errors    -- bledy parsowania
audit_log        -- KAZDA zmiana danych (kto, kiedy, co, stare/nowe, UTC)
```

Indeksy: timestamp, username, session_id, source_file

---

## SESJA - BUDOWANIE Z EVENTOW

Algorytm session_builder:
1. Session start -> zapamietaj usera i czas
2. Zbieraj eventy GVL open/close - kazda para to "GVL cycle"
3. Session finished -> zamknij sesje
4. Sumuj czas GVL cycles = billable_time
5. Jesli 0 cykli GVL -> status = NO_MEASUREMENT
6. Sesja moze miec wiele cykli PUMP -> READY -> GVL -> close -> VENT -> PUMP -> ...

Przyklad z realnego logu:
```
14:04:41 Session started: student
14:07:37 HV ON
14:07:37 GVL open        <- start billable #1
14:18:25 GVL close       <- end billable #1 (10 min 48s)
14:18:29 HV OFF
15:42:48 PUMP
15:45:01 READY
15:51:47 HV ON
15:51:47 GVL open        <- start billable #2
17:02:45 GVL close       <- end billable #2 (70 min 58s)
17:02:48 HV heating OFF
17:02:51 HV OFF
17:07:35 Session finished
TOTAL BILLABLE: 81 min 46s
```

---

## PPM MENU (prawy przycisk na sesji)

- Ustaw rabat % (zmniejsza czas procentowo)
- Odejmij godziny od rozliczenia (np. -2h z 12h = rozliczamy 10h)
- Ustaw kwote na sztywno (PLN)
- Ustaw czas recznie (minuty)
- Wyklucz z faktury (toggle)
- Anuluj sesje (cancelled, cost=0)
- Pokaz wykres HV (otwiera tab_hv_charts dla tej sesji)

Kazda operacja -> audit_log.

---

## IMPORT I USUWANIE PLIKOW

### Import:
- Add Files... - wybor plikow
- Scan Folder... - rekurencyjnie
- Auto-detekcja typu (HISTORY / HV) po nazwie pliku
- Incremental: skip juz zaimportowanych (hash check)
- Walidacja: monotonicznosc timestampow

### Usuwanie:
- W tab Dashboard: lista zaimportowanych plikow
- Przycisk "Remove" / klawisz Delete
- Usuwa WSZYSTKIE dane powiazane z tym plikiem:
  - sesje (WHERE source_file = ?)
  - vacuum_cycles (WHERE source_file = ?)
  - hv_samples (WHERE source_file = ?)
  - anomalies (WHERE source_file = ?)
  - sam wpis w file_cache
- Potwierdzenie dialogiem "Na pewno usunac? Zostanie usuniete X sesji, Y cykli..."
- Audit log: kto usunol, kiedy, jaki plik, ile rekordow

---

## ZAKLADKI GUI (7)

1. Dashboard - statystyki + import/usuwanie plikow
2. Sessions - lista sesji + filtry + PPM menu
3. Vacuum - cykle + kary + anomalie pompowania
4. Usage Heatmaps - heatmapy z custom kolorami
5. HV Charts - wykresy z multi-axis, zoom, pan, log scale, units
6. Settings - stawka PLN/h, uzytkownicy, progi anomalii, backup
7. Help - manual

---

## AUDIT TRAIL

Kazda modyfikacja danych -> wpis:
- action (IMPORT/DELETE_FILE/EDIT/CANCEL/OVERRIDE_COST/OVERRIDE_TIME/CHANGE_DISCOUNT...)
- entity_type + entity_id
- changed_by (current operator)
- old_value, new_value (JSON)
- created_at (UTC)

---

## BACKUP

- Auto-backup przy starcie (konfigurowalne)
- Rolling: usuwaj starsze niz 30 dni
- Monthly snapshot (nie usuwany)
- Reczny backup z Settings

---

## BUILD

- `build.bat` -> PyInstaller --onedir --windowed
- `run_dev.bat` -> venv + python main.py
- Wynik: folder dist/tescan_logger/ (zipnij do dystrybucji)

---

## DODATKOWE ZASADY

- Brak em-dash (--) w kodzie - tylko zwykly minus (-)
- Brak strzalek unicode - tylko ->
- Komentarze po angielsku (spojnie)
- Moduly <400 linii
- Obsluga wyjatkow wszedzie (DB, IO, parse)
- Offline - zero zaleznosci sieciowych
- Na razie TYLKO VEGA3 (MIRA3 w przyszlosci)
