# main.py
import streamlit as st
import pandas as pd
import re
import time
import asyncio
import os
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ── Detect if running on Streamlit Cloud ─────────────────────────────────────
is_cloud = os.environ.get("STREAMLIT_SERVER_ENABLE_STATIC_SERVING", False)

# ── Driver Factory ───────────────────────────────────────────────────────────
@st.cache_resource
def init_driver():
    chrome_options = Options()

    # Must-have for Streamlit Cloud
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,900")

    # Anti-detection / stealth flags (helps vs Cloudflare)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # Always force headless on cloud — visible mode impossible there
    if is_cloud:
        chrome_options.add_argument("--headless=new")
        st.info("Running in headless mode (required on Streamlit Cloud — no display server available)")
    else:
        # Local run → allow user to choose visible/headless
        if not st.session_state.get("headless", True):
            st.info("Visible browser mode activated (local run only)")

    try:
        # Selenium Manager automatically downloads compatible chromedriver
        service = Service()                     # ← this is the key line
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    except Exception as e:
        st.error("Failed to initialize Chrome driver")
        st.error(str(e))
        st.error("Common causes:\n• Missing 'chromium' in packages.txt\n• Selenium < 4.6\n• Container resource limits")
        st.stop()

# ── Scraping function ────────────────────────────────────────────────────────
def scrape_ahrefs_traffic(driver, url, max_wait):
    result = {
        "URL": url,
        "Website": "Error",
        "Organic Traffic": "Error",
        "Traffic Value": "N/A",
        "Top Country": "N/A",
        "Top Country Share": "N/A",
        "Top Keyword": "N/A",
        "Keyword Position": "N/A",
        "Top Keyword Traffic": "N/A",
        "Status": "Failed",
        "Debug": ""
    }

    try:
        target = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(target)

        time.sleep(3.5)  # short initial delay

        # Wait for Cloudflare clearance cookie
        cleared = False
        start = time.time()
        while time.time() - start < max_wait:
            if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                cleared = True
                break
            time.sleep(1.2)

        if not cleared:
            result["Debug"] = "Cloudflare clearance cookie not found → likely blocked"

        # Wait for the result modal
        WebDriverWait(driver, max_wait - 4).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(locator_type, value):
            try:
                return modal.find_element(locator_type, value).text.strip()
            except:
                return "N/A"

        result["Website"]       = safe_text(By.CSS_SELECTOR, "h2") or "N/A"

        result["Organic Traffic"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[contains(@class,'css-vemh4e') or contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[2]/div/div/div/span")

        result["Traffic Value"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[starts-with(text(),'$') or contains(@class,'css-6s0ffe')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[2]/div[2]/div/div/div/span")

        # Top country row
        country_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(1) tr:first-child")
        if country_row != "N/A":
            m = re.match(r"(.+?)\s+([\d\.]+%)", country_row.strip())
            if m:
                result["Top Country"] = m.group(1).strip()
                result["Top Country Share"] = m.group(2)

        # Top keyword row
        kw_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(2) tr:first-child")
        if kw_row != "N/A":
            m = re.match(r"(.+?)\s+(\d+)\s+([\d,K,M\.]+)", kw_row.strip())
            if m:
                result["Top Keyword"] = m.group(1)
                result["Keyword Position"] = m.group(2)
                result["Top Keyword Traffic"] = m.group(3)

        result["Status"] = "Success"
        result["Debug"] = "OK"

    except Exception as e:
        result["Organic Traffic"] = f"Error: {str(e)[:90]}…"
        result["Status"] = "Failed"
        result["Debug"] = traceback.format_exc()[:450].replace("\n", "  ")

    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait_sec):
    driver = init_driver()
    executor = ThreadPoolExecutor(max_workers=1)  # conservative on cloud
    loop = asyncio.get_event_loop()

    results = []
    total = len(urls)
    start_time = time.time()

    progress_bar = st.progress(0)
    status_text = st.empty()
    result_table = st.empty()

    for i, url in enumerate(urls):
        row = await loop.run_in_executor(executor, scrape_ahrefs_traffic, driver, url, max_wait_sec)
        results.append(row)

        progress = (i + 1) / total
        elapsed = time.time() - start_time
        eta_min = round(((elapsed / (i + 1)) * (total - i - 1)) / 60, 1) if i < total - 1 else 0
        successes = sum(1 for r in results if r["Status"] == "Success")

        status_text.markdown(
            f"**Progress:** {i+1}/{total} • **Success:** {successes} • **ETA:** ~{eta_min} min"
        )
        progress_bar.progress(progress)
        result_table.dataframe(pd.DataFrame(results))

    driver.quit()
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="wide")

st.title("Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 edition • Cloudflare protection is very aggressive → expect partial success")

col1, col2 = st.columns([3, 1])

with col1:
    uploaded_file = st.file_uploader("Upload CSV or XLSX with URLs", type=["csv", "xlsx"])

with col2:
    max_wait = st.number_input("Max wait per site (seconds)", 20, 240, 75, step=5)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        url_column = st.selectbox("Select column containing URLs", options=df.columns)
        urls = df[url_column].dropna().astype(str).unique().tolist()

        st.markdown(f"**Found {len(urls)} unique URLs**")

        if st.button("▶️  Start Processing", type="primary", use_container_width=True):
            with st.spinner("Initializing browser..."):
                results = asyncio.run(process_urls(urls, max_wait))

            st.success("Processing finished!")
            if results:
                final_df = pd.DataFrame(results)
                csv_bytes = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Results as CSV",
                    data=csv_bytes,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y-%m-%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"Error reading file: {str(e)}")

st.markdown("---")
st.caption(
    "**Important 2026 notes**\n"
    "• Always headless on Streamlit Cloud (no graphical display)\n"
    "• Cloudflare detects & blocks headless Chrome aggressively\n"
    "• Use the **Debug** column to understand failures\n"
    "• For manual captcha solving → run locally and disable headless"
)
