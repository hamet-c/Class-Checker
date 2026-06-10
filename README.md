# CUNY Class Checker

A Python script that monitors CUNY Global Class Search for open seats in a specific course and alerts you when a spot opens up — via Discord notification (cloud mode) or Windows popup (local mode).

## How It Works

The script uses Selenium to periodically scrape [CUNY Global Class Search](https://globalsearch.cuny.edu/) and checks the enrollment status of your target course. When a section is Open, you get notified.

- **Cloud mode (recommended):** GitHub Actions checks ~12 times a day (every 2 hours) on GitHub's servers and pings a Discord webhook when a seat opens. Your computer can be off.
- **Local mode:** loops every ~3 minutes with random jitter and shows a Windows MessageBox popup.
- Logs each check result to `class_checker.log`
- Uses the status image filename (`status_open.gif` / `status_closed.gif`) instead of the alt text, since CUNY's alt tags are unreliable

## Running in the Cloud (GitHub Actions + Discord)

Two workflows:

- **Class Checker** (`class-check.yml`): one quick check every 2 hours (~12/day), at :23 past even UTC hours. GitHub's cron is best-effort, so expect some jitter in exact timing.
- **Manual Check** (`manual-check.yml`): one instant check on demand. Use this to test or to check right now.

One-time setup:

1. **Create a Discord webhook:** in any Discord server you control → Server Settings → Integrations → Webhooks → New Webhook → pick the channel → Copy Webhook URL. (Keep the URL secret — anyone with it can post to your channel.)
2. **Add it as a repo secret:** GitHub repo → Settings → Secrets and variables → Actions → New repository secret. Name: `DISCORD_WEBHOOK_URL`, value: the webhook URL.
3. **Test it:** Actions tab → Manual Check → Run workflow → check "send a test Discord ping" → Run. You should get a test message in Discord plus a real check.
4. In Discord, set that channel's notification setting to **All Messages** so webhook pings buzz your phone (webhooks can't use @mentions reliably).

Notes:

- The repo must stay **public** — private repos cap free Actions minutes at 2,000/month, a few days of checking.
- GitHub auto-disables scheduled workflows after 60 days with no repo activity — push any commit (or click "Enable" in the Actions tab) to keep it alive.
- Check results appear in each run's log and step summary in the Actions tab. A failed scrape shows as a red run and simply gets retried at the next scheduled check.

## Requirements (local mode)

- Python 3.10+
- Google Chrome
- Windows (uses `ctypes` MessageBox for notifications)

## Setup

```bash
pip install -r requirements.txt
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
WATCH_CLASS_NUMBERS = ["19247", "19240"]  # Alert only for these class numbers ([] = any section)
CHECK_INTERVAL_SECONDS = 180      # How often to check (seconds)
JITTER_SECONDS = 30               # Random delay added/subtracted each cycle
```

`WATCH_CLASS_NUMBERS` uses the 5-digit "Class" column from the search results, so you can target specific sections (e.g. a particular time slot or instructor) and ignore ones you don't want — like the section you're already enrolled in. Sections that aren't watched still appear in the logs, just without alerts.

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

### Single check (what the cloud runs)

```bash
python Main.py --once
```

Runs one check and exits (exit code 1 if the scrape failed or the course wasn't found). Set the `DISCORD_WEBHOOK_URL` environment variable to also get a Discord ping; add `--test-notify` to send a test ping first.

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
