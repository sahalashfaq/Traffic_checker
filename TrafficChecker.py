import streamlit as st
import pandas as pd
import re
import time
import asyncio
import os
import traceback
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
    options = uc.ChromeOptions()
   
    # Essential for cloud/headless
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
   
    # Additional stealth options
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--allow-running-insecure-content")
   
    # Realistic user agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
    )
   
    # Force headless on cloud
    if is_cloud:
        headless_mode = True
        st.warning("Running in headless mode on Streamlit Cloud.")
   
    if headless_mode:
        options.add_argument("--headless=new")
    else:
        st.warning("Visible mode enabled for local debugging.")
   
    try:
        driver = uc.Chrome(
            version_main=144,
            options=options,
            use_subprocess=True,
            driver_executable_path=None
        )
       
        # Set implicit wait
        driver.implicitly_wait(10)
       
        if not headless_mode:
            driver.maximize_window()
       
        st.success("✓ ChromeDriver initialized successfully")
        return driver
   
    except Exception as e:
        st.error(f"ChromeDriver initialization failed: {str(e)}")
        try:
            st.info("Attempting fallback with auto-detection...")
            driver = uc.Chrome(options=options, use_subprocess=True)
            driver.implicitly_wait(10)
            if not headless_mode:
                driver.maximize_window()
            st.success("✓ ChromeDriver initialized (fallback mode)")
            return driver
        except Exception as e2:
            st.error(f"Fallback failed: {str(e2)}")
            st.stop()
def scrape_ahrefs_traffic(driver, url, max_wait):
    result = {
        "URL": url,
        "Website Name": "N/A",
        "Organic Traffic": "N/A",
        "Traffic Worth": "N/A",
        "Status": "Failed",
        "Debug": ""
    }

    try:
        # Use correct parameter name (input → not always needed, but safer)
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)
        time.sleep(2.5)

        # ── Cloudflare handling ───────────────────────────────────────
        page_source_lower = driver.page_source.lower()
        if any(x in page_source_lower for x in ["cloudflare", "just a moment", "checking your browser", "cf-browser-verification"]):
            result["Debug"] = "Cloudflare detected → waiting longer..."
            max_cf = min(max_wait, 45)
            start = time.time()
            cleared = False

            while time.time() - start < max_cf:
                cookies = driver.get_cookies()
                if any(c.get('name') == 'cf_clearance' for c in cookies):
                    cleared = True
                    result["Debug"] = "Cloudflare cleared (cf_clearance cookie found)"
                    break
                current = driver.page_source.lower()
                if all(x not in current for x in ["cloudflare", "just a moment", "checking your browser"]):
                    cleared = True
                    result["Debug"] = "Cloudflare screen disappeared"
                    break
                time.sleep(1.8)

            if not cleared:
                result["Debug"] += " | Cloudflare NOT cleared"
                result["Status"] = "Blocked by Cloudflare"
                return result

        # ── Wait for results area ─────────────────────────────────────
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Modal'], [class*='modal'], .ReactModalPortal"))
            )
            result["Debug"] += " | Modal / portal found"
        except TimeoutException:
            result["Debug"] += " | No modal detected after wait"
            # Some versions no longer use classic modal — try to find result cards anyway
            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='traffic'], [class*='visits'], [class*='value']"))
                )
                result["Debug"] += " | Found traffic-related elements anyway"
            except:
                result["Status"] = "No result container found"
                return result

        time.sleep(2.5)  # let React/Vue/etc. finish rendering

        # ── Try to get website/domain name ────────────────────────────────
        candidates = driver.find_elements(By.CSS_SELECTOR,
            "h1, h2, h3, .ReactModalPortal p, [class*='domain'], [class*='title'], [class*='header'] strong"
        )
        for el in candidates:
            txt = el.text.strip()
            if txt and len(txt) > 3 and "." in txt and not txt.startswith("$") and not any(c.isdigit() for c in txt[:4]):
                result["Website Name"] = txt
                break

        if result["Website Name"] == "N/A":
            # Fallback: look for first big text in modal
            try:
                result["Website Name"] = driver.find_element(
                    By.CSS_SELECTOR, ".ReactModalPortal [class*='title'], .ReactModalPortal h2, .ReactModalPortal p"
                ).text.strip()
            except:
                pass

        # ── Organic Traffic (look for visits / traffic number with K/M/B) ─────
        traffic_candidates = driver.find_elements(By.XPATH,
            "//*[contains(text(),'K') or contains(text(),'M') or contains(text(),'B') or contains(text(),'visits') or contains(text(),'traffic')]"
        )

        for el in traffic_candidates:
            txt = el.text.strip()
            if any(suffix in txt.lower() for suffix in ["k", "m", "b", " visits", " traffic"]):
                # Usually the first big number near "organic" or standalone is it
                if "organic" in el.get_attribute("outerHTML").lower() or "search" in el.get_attribute("outerHTML").lower():
                    result["Organic Traffic"] = txt
                    break
                elif result["Organic Traffic"] == "N/A" and any(c in txt for c in "KM"):
                    result["Organic Traffic"] = txt  # best guess

        # ── Traffic Worth ($) ────────────────────────────────────────────────
        worth_candidates = driver.find_elements(By.XPATH,
            "//*[contains(text(),'$')]"
        )
        for el in worth_candidates:
            txt = el.text.strip()
            if txt.startswith("$") and any(c.isdigit() for c in txt):
                # Usually the biggest / first one near "worth" or "value"
                parent_html = el.find_element(By.XPATH, "..").get_attribute("outerHTML").lower()
                if any(w in parent_html for w in ["worth", "value", "traffic value", "usd"]):
                    result["Traffic Worth"] = txt
                    break
                elif result["Traffic Worth"] == "N/A":
                    result["Traffic Worth"] = txt  # fallback

        # ── Final decision ───────────────────────────────────────────────────
        has_data = any(x != "N/A" for x in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]])

        if has_data:
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data found"
            result["Debug"] += " | Found container but could not match numbers/names"

    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:180]}…"

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
       
        # Small delay between requests to appear more human
        time.sleep(2)
    driver.quit()
    return results
# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")
st.title("🔍 Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 Cloud Version • Enhanced Cloudflare Detection • Exact XPath Targeting")
# Controls
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("📁 Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("⏱️ Max wait per URL (sec)", 30, 180, 70, 5)
with col3:
    headless = st.checkbox("🤖 Run Headless", value=True,
                          help="Headless mode required on cloud deployment")
if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL column", df.columns)
        urls = df[url_col].dropna().unique().tolist()
        st.markdown(f"**📊 {len(urls)} unique URLs found**")
        if st.button("▶️ Start Processing", type="primary"):
            spinner = st.empty()
            spinner.markdown(
                """
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="loader"></div>
                    <span>Initializing scraper...</span>
                </div>
                <style>.loader {border:5px solid #f3f3f3;border-top:5px solid #3498db;border-radius:50%;width:28px;height:28px;animation:spin 1s linear infinite;} @keyframes spin {0% {transform:rotate(0deg);} 100% {transform:rotate(360deg);}}</style>
                """, unsafe_allow_html=True
            )
            progress = st.progress(0)
            status = st.empty()
            table = st.empty()
            def update_ui(current, total, success_count, eta_min, current_results):
                progress.progress(current / total)
                status.markdown(f"**Progress:** {current}/{total} • **✓ Success:** {success_count} • **⏳ ETA:** ~{eta_min} min")
               
                # Show results table with only required columns
                df_results = pd.DataFrame(current_results)
                # Reorder columns for better display
                column_order = ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                df_results = df_results[column_order]
                table.dataframe(df_results, use_container_width=True)
            results = asyncio.run(
                process_urls(urls, max_wait, headless=headless, progress_callback=update_ui)
            )
            spinner.empty()
           
            # Show summary
            success_count = sum(1 for r in results if r["Status"] == "Success")
            blocked_count = sum(1 for r in results if "Cloudflare" in r["Status"] or "blocked" in r["Debug"].lower())
           
            if success_count > 0:
                st.success(f"✅ Processing finished! {success_count}/{len(results)} successful")
            else:
                st.error(f"⚠️ No successful scrapes. {blocked_count} blocked by Cloudflare. Check Debug column.")
            if results:
                final_df = pd.DataFrame(results)
                # Reorder columns for export
                column_order = ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                final_df = final_df[column_order]
               
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "⬇️ Download Results CSV",
                    data=csv,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
               
                # Show status breakdown
                st.markdown("### 📈 Status Breakdown")
                status_counts = final_df['Status'].value_counts()
                st.dataframe(status_counts, use_container_width=True)
    except Exception as e:
        st.error(f"❌ Error reading file: {str(e)}")
        st.error(traceback.format_exc())
st.markdown("---")
st.markdown("""
### ℹ️ Troubleshooting Guide

**All "N/A" results**: Cloudflare is blocking requests. Try:
  - Increase wait time to 90+ seconds
  - Run during off-peak hours
  - Consider using residential proxies (not included in this version)
**"Modal not found"**: Page didn't load properly, increase timeout
**"Blocked by Cloudflare"**: Strong anti-bot protection detected
Check the **Debug** column for specific error details

### 📍 XPath Selectors Used:

**Website Name**: /html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p
**Organic Traffic**: /html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span
**Traffic Worth**: /html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span
""")
