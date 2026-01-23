# main.py
import streamlit as st
import pandas as pd
import re
import time
import asyncio
import os
import traceback
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ── Detect if on Streamlit Cloud ─────────────────────────────────────────────
is_cloud = os.environ.get("STREAMLIT_SERVER_ENABLE_STATIC_SERVING", False)

# ── Driver Factory ───────────────────────────────────────────────────────────
@st.cache_resource
def init_driver(headless_mode=True):
    chrome_options = Options()
    
    # Essential cloud flags
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,900")
    
    # Anti-detection / stealth (helps vs Cloudflare)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    
    if is_cloud:
        headless_mode = True
        st.warning("Visible mode disabled on Streamlit Cloud. Running headless.")
    
    if headless_mode:
        chrome_options.add_argument("--headless=new")
    else:
        st.warning("Visible mode: local debugging only. Solve captchas manually if needed.")
    
    try:
        # Clear old cached drivers (prevents stuck old versions like 114)
        cache_dir = os.path.expanduser("~/.cache/selenium")
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                st.info("Cleared old Selenium/WebDriver cache to force fresh download.")
            except Exception as clear_err:
                st.warning(f"Cache clear failed: {clear_err}")
        
        # Force driver version matching Chromium ~144 on Streamlit Cloud (2026)
        # Use driver_version= (not version=) → this is the fix for your error
        driver_path = ChromeDriverManager(
            driver_version="144.0.5733.199"   # or try "144" / "latest" if this patch fails
        ).install()
        
        service = Service(driver_path)
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        if not headless_mode:
            driver.maximize_window()
        return driver
    
    except Exception as e:
        st.error("Chromium driver failed to start")
        st.error(str(e))
        st.error("Tip: Check backend logs. Common fixes: version mismatch, cache issues, or missing chromium package.")
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
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)
        
        time.sleep(4)
        
        # Cloudflare wait
        start_cf = time.time()
        cleared = False
        while time.time() - start_cf < max_wait:
            if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                cleared = True
                break
            time.sleep(1.5)
        
        if not cleared:
            result["Debug"] = "No cf_clearance cookie after wait → likely blocked by Cloudflare"
        
        WebDriverWait(driver, max_wait - 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )
        
        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")
        
        def safe_text(by, value):
            try:
                return modal.find_element(by, value).text.strip()
            except:
                return "N/A"
        
        result["Website"] = safe_text(By.CSS_SELECTOR, "h2") or "N/A"
        
        result["Organic Traffic"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[contains(@class,'css-vemh4e') or contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[2]/div/div/div/span")
        
        result["Traffic Value"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[starts-with(text(),'$') or contains(@class,'css-6s0ffe')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[2]/div[2]/div/div/div/span")
        
        country_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(1) tr:first-child")
        if country_row != "N/A":
            match = re.match(r"(.+?)\s+([\d.%]+)", country_row.strip())
            if match:
                result["Top Country"] = match.group(1).strip()
                result["Top Country Share"] = match.group(2)
        
        kw_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(2) tr:first-child")
        if kw_row != "N/A":
            match = re.match(r"(.+?)\s+(\d+)\s+([\d,K,M\.]+)", kw_row.strip())
            if match:
                result["Top Keyword"] = match.group(1)
                result["Keyword Position"] = match.group(2)
                result["Top Keyword Traffic"] = match.group(3)
        
        result["Status"] = "Success"
        result["Debug"] = "OK"
    
    except Exception as e:
        result["Organic Traffic"] = f"Error: {str(e)[:80]}..."
        result["Status"] = "Failed"
        result["Debug"] = traceback.format_exc()[:400]
    
    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    driver = init_driver(headless_mode=headless)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    
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

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("Max wait per URL (sec)", 30, 180, 70, 5)
with col3:
    headless = st.checkbox("Run Headless", value=True,
                          help="Uncheck for visible browser (local debugging only; won't work on cloud)")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL column", df.columns)
        urls = df[url_col].dropna().unique().tolist()

        st.markdown(f"**{len(urls)} unique URLs found**")

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
st.caption("**2026 Notes:** Headless only on cloud. Check 'Debug' column. Cloudflare blocks → partial success expected. If driver still fails, try driver_version='144' or 'latest'.")
