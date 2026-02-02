# main.py
import streamlit as st
import pandas as pd
import time
import asyncio
import os
import traceback
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import undetected_chromedriver as uc   # keep as fallback

# ── Custom CSS (if you have style.css) ───────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass
local_css("style.css")

is_cloud = os.environ.get("STREAMLIT_SERVER_ENABLE_STATIC_SERVING", False)

# ── Try system Chromium first (requires packages.txt), fallback to uc auto ───
def create_driver(headless=True):
    status = st.empty()
    status.caption("Trying to initialize browser...")

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

    if is_cloud or headless:
        chrome_options.add_argument("--headless=new")

    driver = None

    # Attempt 1: Standard Selenium + webdriver_manager (downloads matching driver)
    try:
        status.caption("Attempt 1: webdriver_manager auto-install...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.implicitly_wait(10)
        status.caption("✓ Success with standard Selenium + webdriver_manager")
        return driver
    except Exception as e:
        status.caption(f"webdriver_manager failed: {str(e)[:120]} → fallback")

    # Attempt 2: undetected_chromedriver auto (no version_main)
    try:
        status.caption("Attempt 2: undetected_chromedriver auto-detect...")
        uc_options = uc.ChromeOptions()
        for arg in chrome_options.arguments:
            uc_options.add_argument(arg)
        driver = uc.Chrome(options=uc_options, use_subprocess=True)
        driver.implicitly_wait(10)
        status.caption("✓ Success with undetected_chromedriver auto")
        return driver
    except Exception as e:
        status.caption(f"undetected auto failed: {str(e)[:120]}")

    status.error("❌ All browser init attempts failed. Add packages.txt with chromium + chromium-driver and redeploy.")
    raise RuntimeError("Browser could not be started")

# ── Scrape function (same logic as before) ───────────────────────────────────
def scrape_ahrefs_traffic(url, max_wait, headless):
    result = {
        "URL": url,
        "Website Name": "N/A",
        "Organic Traffic": "N/A",
        "Traffic Worth": "N/A",
        "Status": "Failed",
        "Debug": ""
    }

    driver = None
    try:
        driver = create_driver(headless_mode=headless)

        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)
        time.sleep(3 + random.uniform(0, 2))

        # Cloudflare handling (same as before)
        page_lower = driver.page_source.lower()
        if any(p in page_lower for p in ["cloudflare", "just a moment", "checking your browser"]):
            result["Debug"] = "Cloudflare → waiting..."
            start = time.time()
            cleared = False
            while time.time() - start < min(max_wait, 40):
                try:
                    if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                        cleared = True
                        break
                    if "cloudflare" not in driver.page_source.lower():
                        cleared = True
                        break
                except:
                    pass
                time.sleep(2)
            result["Debug"] += " cleared" if cleared else " failed"
            if not cleared:
                result["Status"] = "Blocked by Cloudflare"
                return result

        # Modal wait (same)
        try:
            WebDriverWait(driver, max_wait).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal")))
            result["Debug"] += " | Modal OK"
        except TimeoutException:
            result["Debug"] += " | No modal"
            result["Status"] = "Timeout"
            return result

        time.sleep(2.5 + random.uniform(0, 1.5))

        # Extraction (your original XPaths + fallbacks - abbreviated for brevity)
        def safe_text(by, val):
            try:
                return driver.find_element(by, val).text.strip() or "N/A"
            except:
                return "N/A"

        result["Website Name"] = safe_text(By.XPATH, "/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p") or \
                                 safe_text(By.CSS_SELECTOR, ".ReactModalPortal h2")

        result["Organic Traffic"] = safe_text(By.XPATH, "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span") or \
                                    safe_text(By.XPATH, "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]")

        result["Traffic Worth"] = safe_text(By.XPATH, "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span") or \
                                  safe_text(By.XPATH, "//span[contains(text(),'$')]")

        if any(v != "N/A" for v in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]]):
            result["Status"] = "Success"
        else:
            result["Status"] = "No data"

    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = str(e)[:150]

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        time.sleep(1.2)

    return result

# Batch & UI code remains almost identical - abbreviated here to save space
# (copy your previous process_urls, UI, file upload, progress, download logic)
# Just update the scrape call to use the new create_driver

# ... paste your existing async process_urls and st UI code here ...
# The only change is in scrape_ahrefs_traffic: driver = create_driver(headless)

# At the end:
st.caption("Important: Add packages.txt in repo root with 'chromium' and 'chromium-driver' for best chance on cloud.")
