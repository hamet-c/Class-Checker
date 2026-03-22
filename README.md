# CUNY Class Checker

A Python script that monitors CUNY Global Class Search for open seats in a specific course and alerts you with a Windows popup when a spot opens up.

## How It Works

The script uses Selenium to periodically scrape [CUNY Global Class Search](https://globalsearch.cuny.edu/) and checks the enrollment status of your target course. When a section changes from Closed to Open, you get a Windows MessageBox popup.

- Checks every ~3 minutes with random jitter to avoid detection
- Runs silently in the background (`.pyw` version) or in a terminal (`.py` version)
- Logs each check result to `class_checker.log`
- Uses the status image filename (`status_open.gif` / `status_closed.gif`) instead of the alt text, since CUNY's alt tags are unreliable

## Requirements

- Python 3.10+
- Google Chrome
- Windows (uses `ctypes` MessageBox for notifications)

## Setup

```bash
pip install selenium webdriver-manager
```

## Configuration

Edit the variables at the top of `Main.pyw` (or `Main.py`):

```python
COLLEGE = "City College"          # College name (must match dropdown text)
COLLEGE_CODE = "CTY01"            # Institution code
TERM = "2026 Fall Term"           # Term (must match dropdown text)
SUBJECT = "Computer Science"      # Subject (must match dropdown text)
COURSE_CAREER = "Undergraduate"   # "Undergraduate", "Graduate", "Doctoral", or ""
COURSE_NUMBER = "30400"           # Course number to watch
CHECK_INTERVAL_SECONDS = 180      # How often to check (seconds)
JITTER_SECONDS = 30               # Random delay added/subtracted each cycle
```

### College Codes

| Code  | College          |
|-------|------------------|
| CTY01 | City College     |
| HTR01 | Hunter College   |
| QNS01 | Queens College   |
| BAR01 | Baruch College   |
| BKL01 | Brooklyn College |
| LEH01 | Lehman College   |
| JJC01 | John Jay College |
| YRK01 | York College     |

## Usage

### Background mode (no terminal window)

Double-click `Main.pyw` or run:

```bash
pythonw Main.pyw
```

A popup confirms the script is running. To stop it, end `pythonw.exe` in Task Manager.

### Terminal mode (with console output)

```bash
python Main.py
```

Stop with `Ctrl+C`.

## Log Output

Each check writes one line to `class_checker.log`:

```
03/18/2026 06:45:32 PM — Closed — All sections: Closed, Closed
03/18/2026 06:48:41 PM — Closed — All sections: Closed, Closed
03/18/2026 06:51:55 PM — OPEN — 1 of 2 section(s) OPEN
```

## Notes

- CUNY's seat availability updates instantly when someone drops a class
- The script uses randomized delays and a realistic user-agent to avoid rate limiting
- The "Show Open Classes Only" filter is automatically unchecked so all sections are visible regardless of status
