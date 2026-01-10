# main.py
import streamlit as st
import pandas as pd
import re
import time
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ── Driver Factory ───────────────────────────────────────────────────────────
@st.cache_resource
def init_driver(headless_mode=True):
    chrome_options = Options()
    
    # Common options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,900")
    
    # Headless or visible mode
    if headless_mode:
        chrome_options.add_argument("--headless=new")
    else:
        st.warning("Running in VISIBLE mode – browser window will appear (only useful locally)")

    # Important for Streamlit Cloud (Debian Bookworm)
    chrome_options.binary_location = "/usr/bin/chromium"

    service = Service(executable_path="/usr/bin/chromedriver")

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        if not headless_mode:
            driver.maximize_window()
        return driver
    except Exception as e:
        st.error("Chromium driver initialization failed")
        st.error(str(e))
        st.stop()

# ── Updated scraping function with better selectors ──────────────────────────
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
        "Status": "Failed"
    }

    try:
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)

        time.sleep(5)  # initial Cloudflare breathing room

        # Try to wait for clearance (best effort)
        start_cf = time.time()
        while time.time() - start_cf < max_wait:
            if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                break
            time.sleep(1.5)

        # Wait for modal to appear
        WebDriverWait(driver, max_wait - 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(by, value):
            try:
                return modal.find_element(by, value).text.strip()
            except:
                return "N/A"

        # Updated selectors based on your provided XPath structure
        result["Website"] = safe_text(By.CSS_SELECTOR, "h2") or "N/A"

        # Traffic amount - main big number
        result["Organic Traffic"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[contains(@class,'css-vemh4e') or contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[2]/div/div/div/span")

        # Traffic value (usually $X.XX)
        result["Traffic Value"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[starts-with(text(),'$') or contains(@class,'css-6s0ffe')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[2]/div[2]/div/div/div/span")

        # Top country
        country_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(1) tr:first-child")
        if country_row != "N/A":
            match = re.match(r"(.+?)\s+([\d.%]+)", country_row.strip())
            if match:
                result["Top Country"] = match.group(1).strip()
                result["Top Country Share"] = match.group(2)

        # Top keyword
        kw_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(2) tr:first-child")
        if kw_row != "N/A":
            match = re.match(r"(.+?)\s+(\d+)\s+([\d,K,M\.]+)", kw_row.strip())
            if match:
                result["Top Keyword"] = match.group(1)
                result["Keyword Position"] = match.group(2)
                result["Top Keyword Traffic"] = match.group(3)

        result["Status"] = "Success"

    except Exception as e:
        result["Organic Traffic"] = f"Error: {str(e)[:70]}..."
        result["Status"] = "Failed"

    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    driver = init_driver(headless_mode=headless)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=2)  # 2 is safer in visible mode

    results = []
    total = len(urls)
    start = time.time()

    for i, url in enumerate(urls):
        row = await loop.run_in_executor(executor, scrape_ahrefs_traffic, driver, url, max_wait)
        results.append(row)

        elapsed = time.time() - start
        eta = (elapsed / (i+1)) * (total - i - 1) if i < total-1 else 0

        success = sum(1 for r in results if r["Status"] == "Success")

        if progress_callback:
            progress_callback(i+1, total, success, round(eta/60, 1), results)

    driver.quit()
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")

st.title("Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 Cloud Compatible Version • Cloudflare may block many requests")

# Controls
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("Max wait per URL (sec)", 30, 180, 70, 5)
with col3:
    headless = st.checkbox("Run in Headless mode", value=True,
                          help="Uncheck to see browser actions (only useful when running locally)")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL/Domain column", df.columns)
        urls = df[url_col].dropna().unique().tolist()

        st.markdown(f"**{len(urls)} unique URLs/domains found**")

        if st.button("Start Processing", type="primary"):
            spinner = st.empty()
            spinner.markdown(
                """
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="loader"></div>
                    <span>Starting process...</span>
                </div>
                <style>.loader {border:5px solid #f3f3f3;border-top:5px solid #3498db;border-radius:50%;width:28px;height:28px;animation:spin 1s linear infinite;} @keyframes spin {0% {transform:rotate(0deg);} 100% {transform:rotate(360deg);}}</style>
                """, unsafe_allow_html=True
            )

            progress = st.progress(0)
            status = st.empty()
            table = st.empty()

            def update_ui(current, total, success_count, eta_min, current_results):
                progress.progress(current / total)
                status.markdown(f"**Progress:** {current}/{total} • **Success:** {success_count} • **ETA:** ~{eta_min} min")
                table.dataframe(pd.DataFrame(current_results))

            results = asyncio.run(
                process_urls(urls, max_wait, headless=headless, progress_callback=update_ui)
            )

            spinner.empty()
            st.success("Processing finished!")

            if results:
                final_df = pd.DataFrame(results)
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Results CSV",
                    data=csv,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

    except Exception as e:
        st.error(f"Error reading file: {str(e)}")

st.markdown("---")
st.caption("**Important notes 2026:**\n"
           "• On Streamlit Cloud → headless mode only (visible mode works locally)\n"
           "• Cloudflare blocks many requests from cloud IPs → expect 50–80% failure rate\n"
           "• For serious work: use residential proxies or Ahrefs API")
