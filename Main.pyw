import time
import random
import sys
import logging
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager
import ctypes

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

# ============================================================
# END OF USER CONFIGURATION
# ============================================================

SEARCH_URL = "https://globalsearch.cuny.edu/CFGlobalSearchTool/search.jsp"

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler("class_checker.log", encoding="utf-8"),
    ],
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

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.implicitly_wait(10)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def navigate_and_search(driver):
    driver.get(SEARCH_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "t_pd")))
    human_delay(1, 3)

    Select(driver.find_element(By.ID, "t_pd")).select_by_visible_text(TERM)
    human_delay(0.5, 1.5)

    cb = driver.find_element(By.ID, COLLEGE_CODE)
    if not cb.is_selected():
        driver.execute_script("arguments[0].click();", cb)
    human_delay(0.5, 1.0)

    driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "search_new_spin"))
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "subject_ld")))
    human_delay(1, 2)

    Select(driver.find_element(By.ID, "subject_ld")).select_by_visible_text(SUBJECT)
    human_delay(0.5, 1.0)

    if COURSE_CAREER:
        Select(driver.find_element(By.ID, "courseCareerId")).select_by_visible_text(COURSE_CAREER)
        human_delay(0.3, 0.8)

    open_only_cb = driver.find_element(By.ID, "open_class_id")
    if open_only_cb.is_selected():
        driver.execute_script("arguments[0].click();", open_only_cb)
        human_delay(0.2, 0.5)

    driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, 'input[name="search_btn_search"]'))
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.classinfo")))
    human_delay(2, 4)


def parse_results(driver):
    result = {
        "found": False,
        "seats_available": False,
        "details": "",
    }

    page_source = driver.page_source

    if not COURSE_NUMBER:
        result["details"] = "No course number configured"
        return result

    import re
    target_div_idx = None
    for match in re.finditer(r'contentDivImg(\d+)', page_source):
        div_idx = match.group(1)
        start = max(0, match.start() - 600)
        chunk = page_source[start:match.start()]
        if COURSE_NUMBER in chunk:
            target_div_idx = div_idx
            break

    if target_div_idx is None:
        result["details"] = f"Course {COURSE_NUMBER} not found in results"
        return result

    result["found"] = True

    # Find the table inside this contentDiv
    try:
        content_div = driver.find_element(By.ID, f"contentDivImg{target_div_idx}")
        table = content_div.find_element(By.CSS_SELECTOR, "table.classinfo")
    except NoSuchElementException:
        result["details"] = f"Found course header but no table at contentDivImg{target_div_idx}"
        return result

    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    statuses = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 8:
            status_img = cells[7].find_elements(By.TAG_NAME, "img")
            if status_img:
                src = status_img[0].get_attribute("src") or ""
                if "open" in src.lower():
                    statuses.append("Open")
                elif "closed" in src.lower():
                    statuses.append("Closed")
                elif "wait" in src.lower():
                    statuses.append("Wait List")
                else:
                    statuses.append(status_img[0].get_attribute("alt") or "Unknown")
            else:
                statuses.append("Unknown")

    open_sections = [s for s in statuses if s == "Open"]
    if open_sections:
        result["seats_available"] = True
        result["details"] = f"{len(open_sections)} of {len(statuses)} section(s) OPEN"
    else:
        status_summary = ", ".join(statuses) if statuses else "no status found"
        result["details"] = f"All sections: {status_summary}"

    return result


def notify_user(details):
    log.info(f"SEAT AVAILABLE — {details}")
    try:
        ctypes.windll.user32.MessageBoxW(
            0, details[:1024], "CUNY Class Seat Available!", 0x40
        )
    except Exception:
        pass


def main():
    ctypes.windll.user32.MessageBoxW(
        0,
        f"Class Checker is now running in the background.\n\n"
        f"Course: {SUBJECT} {COURSE_NUMBER}\n"
        f"College: {COLLEGE}\n"
        f"Term: {TERM}\n"
        f"Checking every ~{CHECK_INTERVAL_SECONDS // 60} minutes.\n\n"
        f"You will be alerted when a seat opens.\n"
        f"To stop: end 'pythonw.exe' in Task Manager.",
        "Class Checker Started",
        0x40,
    )

    check_count = 0
    driver = None

    try:
        while True:
            check_count += 1
            if 0 < MAX_CHECKS < check_count:
                break

            try:
                driver = create_driver()
                navigate_and_search(driver)
                result = parse_results(driver)

                timestamp = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
                if result["seats_available"]:
                    log.info(f"{timestamp} — OPEN — {result['details']}")
                    notify_user(result["details"])
                else:
                    log.info(f"{timestamp} — Closed — {result['details']}")

            except (TimeoutException, WebDriverException, Exception):
                log.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — Error — retrying next cycle")
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None

            delay = max(60, CHECK_INTERVAL_SECONDS + random.uniform(-JITTER_SECONDS, JITTER_SECONDS))
            time.sleep(delay)

    except KeyboardInterrupt:
        pass
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
