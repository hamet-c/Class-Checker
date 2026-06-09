import json
import os
import time
import random
import sys
import logging
import urllib.request
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

# ============================================================
# USER CONFIGURATION - Edit these values
# ============================================================

# Which CUNY college to search. Use exact label text from the search page.
# Examples: "City College", "Hunter College", "Queens College", "Baruch College"
COLLEGE = "City College"

# Institution code (used internally). Common codes:
#   CTY01=City College, HTR01=Hunter, QNS01=Queens, BAR01=Baruch,
#   BKL01=Brooklyn, LEH01=Lehman, JJC01=John Jay, YRK01=York
COLLEGE_CODE = "CTY01"

# Term to search. Use exact text from the dropdown.
TERM = "2026 Fall Term"

# Subject to select from the dropdown on page 2.
# Use the exact text shown (e.g. "Computer Science", "Mathematics", "Physics").
SUBJECT = "Computer Science"

# Course Career filter. Options: "Undergraduate", "Graduate", "Doctoral", or "" to skip.
COURSE_CAREER = "Undergraduate"

# Course number to look for in results (matched against the course header).
# Example: "30400" will match "CSC 30400 - Software Engineering"
COURSE_NUMBER = "30400"

# How often to check (seconds). Default: 180 = 3 minutes.
CHECK_INTERVAL_SECONDS = 180

# Jitter range (seconds). Actual delay = interval ± random(0, jitter).
JITTER_SECONDS = 30

# Run browser without a visible window. Set False to debug.
HEADLESS = True

# Max check cycles (0 = unlimited, runs until Ctrl+C).
MAX_CHECKS = 0

# Discord notifications: set the DISCORD_WEBHOOK_URL environment variable.
# Never hardcode the webhook URL here -- this repo is public.
# In GitHub Actions it is injected from the DISCORD_WEBHOOK_URL repo secret.
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

# ============================================================
# END OF USER CONFIGURATION
# ============================================================

SEARCH_URL = "https://globalsearch.cuny.edu/CFGlobalSearchTool/search.jsp"

_log_handlers = [logging.FileHandler("class_checker.log", encoding="utf-8")]
if sys.stdout is not None:  # sys.stdout is None under pythonw
    _log_handlers.insert(0, logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_log_handlers,
)
log = logging.getLogger("ClassChecker")


def human_delay(min_s=0.5, max_s=2.0):
    time.sleep(random.uniform(min_s, max_s))


def create_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Selenium Manager (built into Selenium 4.6+) resolves the right
    # chromedriver automatically, locally and on CI runners.
    driver = webdriver.Chrome(options=opts)
    driver.implicitly_wait(10)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def navigate_and_search(driver):
    # ---- Page 1: Select term and institution ----
    log.info("Loading search page...")
    driver.get(SEARCH_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "t_pd"))
    )
    human_delay(1, 3)

    # Select term
    term_dropdown = Select(driver.find_element(By.ID, "t_pd"))
    term_dropdown.select_by_visible_text(TERM)
    log.info(f"Selected term: {TERM}")
    human_delay(0.5, 1.5)

    # Select institution checkbox (hidden by CSS, use JS click)
    cb = driver.find_element(By.ID, COLLEGE_CODE)
    if not cb.is_selected():
        driver.execute_script("arguments[0].click();", cb)
    log.info(f"Selected college: {COLLEGE} ({COLLEGE_CODE})")
    human_delay(0.5, 1.0)

    # Click "Next" to go to page 2
    next_btn = driver.find_element(By.ID, "search_new_spin")
    driver.execute_script("arguments[0].click();", next_btn)
    log.info("Clicked Next, waiting for filter page...")

    # Wait for page 2 to load (subject dropdown appears)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "subject_ld"))
    )
    human_delay(1, 2)

    # ---- Page 2: Select subject, career, and search ----

    # Select subject
    subject_dropdown = Select(driver.find_element(By.ID, "subject_ld"))
    subject_dropdown.select_by_visible_text(SUBJECT)
    log.info(f"Selected subject: {SUBJECT}")
    human_delay(0.5, 1.0)

    # Select course career if configured
    if COURSE_CAREER:
        career_dropdown = Select(driver.find_element(By.ID, "courseCareerId"))
        career_dropdown.select_by_visible_text(COURSE_CAREER)
        log.info(f"Selected career: {COURSE_CAREER}")
        human_delay(0.3, 0.8)

    # Make sure "Show Open Classes Only" is UNCHECKED so we see all classes
    open_only_cb = driver.find_element(By.ID, "open_class_id")
    if open_only_cb.is_selected():
        driver.execute_script("arguments[0].click();", open_only_cb)
        log.info("Unchecked 'Show Open Classes Only'")
        human_delay(0.2, 0.5)

    # Click Search
    search_btn = driver.find_element(By.CSS_SELECTOR, 'input[name="search_btn_search"]')
    driver.execute_script("arguments[0].click();", search_btn)
    log.info("Search submitted, waiting for results...")

    # Wait for results to load
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.classinfo"))
    )
    human_delay(2, 4)
    log.info("Results loaded.")


def parse_results(driver):
    result = {
        "found": False,
        "seats_available": False,
        "details": "",
    }

    # Save screenshot for debugging
    try:
        driver.save_screenshot("last_check.png")
    except Exception:
        pass

    # The results page has course sections grouped as:
    #   <span>...<a id="imageDivLink{N}">...</a> CSC 30400 - Course Name</span>
    #   <div id="contentDivImg{N}"> (collapsed, contains the table)
    #     <table class="classinfo">
    #       <tr><td>...<img alt="Open|Closed|Wait List">...</td></tr>
    #
    # Strategy: search the page source for our course number in the headers,
    # find the matching contentDiv index, then inspect that table's status images.

    page_source = driver.page_source

    if not COURSE_NUMBER:
        # Dump all course headers for inspection
        log.info("No COURSE_NUMBER set. Listing all courses found:")
        links = driver.find_elements(By.CSS_SELECTOR, 'a[id^="imageDivLink"]')
        for link in links:
            span = link.find_element(By.XPATH, "./..")
            log.info(f"  {span.get_attribute('textContent').strip()}")
        result["details"] = "No course number configured — check log for available courses"
        return result

    # Find which contentDiv index has our course
    target_div_idx = None
    import re
    # Match patterns like: CSC&nbsp;30400 or CSC 30400
    for match in re.finditer(r'contentDivImg(\d+)', page_source):
        div_idx = match.group(1)
        # Look at the 600 chars before this div for the course header
        start = max(0, match.start() - 600)
        chunk = page_source[start:match.start()]
        # Check if our course number appears in the header (with &nbsp; or space)
        if COURSE_NUMBER in chunk:
            target_div_idx = div_idx
            # Extract the course title from the chunk
            title_match = re.search(
                r'(?:&nbsp;|[\s])(\w+(?:&nbsp;|\s)' + re.escape(COURSE_NUMBER) + r'(?:&nbsp;|\s)-(?:&nbsp;|\s).+?)</span>',
                chunk,
            )
            if title_match:
                title = title_match.group(1).replace("&nbsp;", " ").replace("&amp;", "&")
                log.info(f"Found course: {title}")
            else:
                log.info(f"Found course number {COURSE_NUMBER} at contentDivImg{div_idx}")
            break

    if target_div_idx is None:
        result["details"] = f"Course {COURSE_NUMBER} not found in results"
        # List what courses are available
        log.info("Available courses:")
        links = driver.find_elements(By.CSS_SELECTOR, 'a[id^="imageDivLink"]')
        for link in links:
            try:
                span = link.find_element(By.XPATH, "./..")
                log.info(f"  {span.get_attribute('textContent').strip()}")
            except Exception:
                pass
        return result

    result["found"] = True

    # Find the table inside this contentDiv
    try:
        content_div = driver.find_element(By.ID, f"contentDivImg{target_div_idx}")
        table = content_div.find_element(By.CSS_SELECTOR, "table.classinfo")
    except NoSuchElementException:
        result["details"] = f"Found course header but no table at contentDivImg{target_div_idx}"
        return result

    # Get section details from each row (use textContent since div is hidden).
    # IMPORTANT: The CUNY site has a bug where the img alt text can be wrong
    # (e.g. alt="Open" but src="status_closed.gif"). We use the image filename
    # as the source of truth for status.
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    statuses = []
    section_details = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 8:
            class_num = (cells[0].get_attribute("textContent") or "").strip()
            section = (cells[1].get_attribute("textContent") or "").strip()
            days_times = (cells[2].get_attribute("textContent") or "").strip()
            instructor = (cells[4].get_attribute("textContent") or "").strip()
            status_img = cells[7].find_elements(By.TAG_NAME, "img")
            if status_img:
                src = status_img[0].get_attribute("src") or ""
                if "open" in src.lower():
                    status = "Open"
                elif "closed" in src.lower():
                    status = "Closed"
                elif "waitlist" in src.lower() or "wait" in src.lower():
                    status = "Wait List"
                else:
                    status = status_img[0].get_attribute("alt") or "Unknown"
            else:
                status = "Unknown"
            statuses.append(status)
            section_details.append(
                f"  Class {class_num} | {section} | {days_times} | {instructor} | {status}"
            )

    log.info(f"Section statuses: {statuses}")
    if section_details:
        log.info("Section details:")
        for detail in section_details:
            log.info(detail)

    # Check if any section is open
    open_sections = [s for s in statuses if s == "Open"]
    if open_sections:
        result["seats_available"] = True
        result["details"] = (
            f"{len(open_sections)} of {len(statuses)} section(s) OPEN for course {COURSE_NUMBER}"
        )
    else:
        result["seats_available"] = False
        status_summary = ", ".join(statuses) if statuses else "no status found"
        result["details"] = f"All sections: {status_summary}"

    return result


def notify_discord(message):
    """Post a message to the Discord webhook. Returns True on success."""
    if not DISCORD_WEBHOOK_URL:
        return False
    payload = json.dumps({"content": message[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "cuny-class-checker"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info(f"Discord notification sent (HTTP {resp.status})")
        return True
    except Exception as e:
        log.error(f"Discord notification failed: {e}")
        return False


def write_step_summary(text):
    """Append a line to the GitHub Actions run summary, if running there."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
    except Exception:
        pass


def notify_user(details):
    log.info("=" * 60)
    log.info("SEAT AVAILABLE! " + details)
    log.info("=" * 60)
    notify_discord(
        ":rotating_light: **CUNY seat available!** :rotating_light:\n"
        f"**{SUBJECT} {COURSE_NUMBER}** at {COLLEGE} ({TERM})\n"
        f"{details}\n"
        f"Enroll now: https://home.cunyfirst.cuny.edu/\n"
        f"Verify: {SEARCH_URL}"
    )
    if sys.platform == "win32" and not os.environ.get("CI"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0, details[:1024], "CUNY Class Seat Available!", 0x40
            )
        except Exception as e:
            log.warning(f"Desktop notification failed: {e}")


def log_config():
    log.info("CUNY Class Checker starting")
    log.info(f"  College:  {COLLEGE} ({COLLEGE_CODE})")
    log.info(f"  Term:     {TERM}")
    log.info(f"  Subject:  {SUBJECT}")
    log.info(f"  Career:   {COURSE_CAREER or '(any)'}")
    log.info(f"  Course:   {COURSE_NUMBER or '(not set — will list courses)'}")
    log.info(f"  Discord:  {'configured' if DISCORD_WEBHOOK_URL else 'not configured'}")


def run_single_check():
    """One full scrape cycle. Returns the parse result dict, or None on error."""
    driver = None
    try:
        driver = create_driver()
        navigate_and_search(driver)
        return parse_results(driver)
    except TimeoutException:
        log.warning("Page load timed out.")
        return None
    except WebDriverException as e:
        log.error(f"Browser error: {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def main_once():
    """Single check, for scheduled runs (GitHub Actions cron).

    Exit 0 when the check completed (seats open or not); exit 1 when the
    scrape failed or the course was missing, so the workflow run shows red.
    """
    log_config()

    if os.environ.get("GITHUB_ACTIONS") and not DISCORD_WEBHOOK_URL:
        log.warning("DISCORD_WEBHOOK_URL secret is not set — open seats will NOT notify you!")
        write_step_summary(
            ":warning: `DISCORD_WEBHOOK_URL` secret is not set — open seats will **not** notify you."
        )

    if os.environ.get("TEST_NOTIFY", "").lower() == "true" or "--test-notify" in sys.argv:
        ok = notify_discord(
            ":white_check_mark: Test ping — the class checker can reach Discord.\n"
            f"Watching **{SUBJECT} {COURSE_NUMBER}** at {COLLEGE} ({TERM})."
        )
        if not ok:
            log.error("Test notification failed. Is the DISCORD_WEBHOOK_URL secret set?")
            write_step_summary(":x: Test notification failed — check the `DISCORD_WEBHOOK_URL` secret.")
            sys.exit(1)

    result = run_single_check()

    if result is None:
        write_step_summary(":warning: Check failed — page did not load or scrape errored.")
        sys.exit(1)
    if not result["found"]:
        log.error(f"Course not found: {result['details']}")
        write_step_summary(f":warning: {result['details']} — term/course config may be stale.")
        sys.exit(1)

    if result["seats_available"]:
        notify_user(result["details"])
        write_step_summary(f":rotating_light: **OPEN** — {result['details']}")
    else:
        log.info(f"No seats: {result['details']}")
        write_step_summary(f"Closed — {result['details']}")


def main():
    log_config()
    log.info(f"  Interval: {CHECK_INTERVAL_SECONDS}s +/- {JITTER_SECONDS}s jitter")
    log.info(f"  Headless: {HEADLESS}")

    check_count = 0
    try:
        while True:
            check_count += 1
            if 0 < MAX_CHECKS < check_count:
                log.info(f"Reached max checks ({MAX_CHECKS}). Exiting.")
                break

            log.info(f"--- Check #{check_count} at {datetime.now().strftime('%H:%M:%S')} ---")
            result = run_single_check()

            if result is None:
                log.info("Check failed, will retry next cycle.")
            elif not result["found"]:
                log.info(f"Course not found: {result['details']}")
            elif result["seats_available"]:
                notify_user(result["details"])
            else:
                log.info(f"No seats: {result['details']}")

            jitter = random.uniform(-JITTER_SECONDS, JITTER_SECONDS)
            delay = max(60, CHECK_INTERVAL_SECONDS + jitter)
            next_time = datetime.now().timestamp() + delay
            next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
            log.info(f"Next check in {delay:.0f}s (at ~{next_str})")
            time.sleep(delay)

    except KeyboardInterrupt:
        log.info("Stopped by user (Ctrl+C).")
    finally:
        log.info("Class Checker shut down.")


if __name__ == "__main__":
    if "--once" in sys.argv:
        main_once()
    else:
        main()
