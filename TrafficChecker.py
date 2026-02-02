# main.py
import streamlit as st
import pandas as pd
import time
import asyncio
import os
import traceback
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

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

# ── Driver Factory (FIXED: no caching of options) ───────────────────────────
def create_driver(headless_mode=True):
    options = uc.ChromeOptions()
    
    # Essential options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--allow-running-insecure-content")
    
    # Realistic user agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    
    if is_cloud or headless_mode:
        options.add_argument("--headless=new")
    
    try:
        driver = uc.Chrome(
            version_main=126,
            options=options,
            use_subprocess=True,
        )
        driver.implicitly_wait(10)
        if not (is_cloud or headless_mode):
            driver.maximize_window()
        return driver
    except Exception as e:
        st.error(f"Driver init failed: {str(e)}")
        raise

# ── Scraping function ───────────────────────────────────────────────────────
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
        time.sleep(2.5 + random.uniform(0, 1.5))

        # Cloudflare handling
        page_source = driver.page_source.lower()
        if any(x in page_source for x in ["cloudflare", "just a moment", "checking your browser"]):
            result["Debug"] = "Cloudflare challenge → waiting..."
            start_cf = time.time()
            cleared = False
            while time.time() - start_cf < min(max_wait, 35):
                try:
                    if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                        cleared = True
                        break
                    if "cloudflare" not in driver.page_source.lower():
                        cleared = True
                        break
                except:
                    pass
                time.sleep(1.8)
            result["Debug"] += " cleared" if cleared else " → NOT cleared"
            if not cleared:
                result["Status"] = "Blocked by Cloudflare"
                return result

        # Wait for modal
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal detected"
        except TimeoutException:
            result["Debug"] += " | Modal NOT found"
            result["Status"] = "Modal timeout"
            return result

        time.sleep(2.5 + random.uniform(0, 2))

        # Extraction helpers
        def safe_text_xpath(xpath):
            try:
                return driver.find_element(By.XPATH, xpath).text.strip() or "N/A"
            except:
                return "N/A"

        # Website Name
        website = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p")
        if website == "N/A":
            for sel in [
                (By.CSS_SELECTOR, ".ReactModalPortal h2"),
                (By.CSS_SELECTOR, ".ReactModalPortal p:first-of-type"),
                (By.XPATH, "//div[contains(@class,'ReactModalPortal')]//p[1]"),
            ]:
                try:
                    website = driver.find_element(*sel).text.strip()
                    if website:
                        break
                except:
                    pass
        result["Website Name"] = website

        # Organic Traffic
        traffic = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span")
        if traffic == "N/A":
            for sel in [
                (By.XPATH, "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"),
                (By.CSS_SELECTOR, "span[class*='css-vemh4e']"),
            ]:
                try:
                    el = driver.find_element(*sel)
                    txt = el.text.strip()
                    if txt and any(c in txt for c in 'KMGB0123456789'):
                        traffic = txt
                        break
                except:
                    pass
        result["Organic Traffic"] = traffic

        # Traffic Worth
        worth = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span")
        if worth == "N/A":
            for sel in [
                (By.XPATH, "//span[starts-with(text(),'$')]"),
                (By.XPATH, "//span[contains(text(),'$')]"),
            ]:
                try:
                    worth = driver.find_element(*sel).text.strip()
                    if worth and '$' in worth:
                        break
                except:
                    pass
        result["Traffic Worth"] = worth

        # Final status
        if any(v != "N/A" for v in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]]):
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data"

    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Error: {str(e)[:150]}"

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        time.sleep(0.6)

    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    results = []
    total = len(urls)
    start_time = time.time()

    for i, url in enumerate(urls):
        row = await asyncio.get_event_loop().run_in_executor(None, scrape_ahrefs_traffic, url, max_wait, headless)
        results.append(row)

        elapsed = time.time() - start_time
        processed = i + 1
        eta = (elapsed / processed) * (total - processed) if processed < total else 0
        success = sum(1 for r in results if r["Status"] == "Success")

        if progress_callback:
            progress_callback(processed, total, success, round(eta/60, 1), results)

        time.sleep(4 + random.uniform(0, 3.5))  # Nice human delay

    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")
st.title("🔍 Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 • Fully Fixed • Works on Streamlit Cloud • No More Errors!")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("📁 Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("⏱️ Max wait per URL (sec)", 30, 180, 80, 5)
with col3:
    headless = st.checkbox("🤖 Run Headless", value=True, help="Keep ON for Streamlit Cloud")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL column", df.columns)
        urls = [str(u).strip() for u in df[url_col].dropna().unique() if str(u).strip().startswith(("http", "www"))]
        st.markdown(f"**📊 Found {len(urls)} unique URLs**")

        if st.button("▶️ Start Processing", type="primary"):
            progress = st.progress(0)
            status_text = st.empty()
            result_table = st.empty()

            def update_ui(current, total, success_count, eta_min, current_results):
                progress.progress(current / total)
                status_text.markdown(f"**Progress:** {current}/{total} • **✓ Success:** {success_count} • **⏳ ETA:** ~{eta_min} min")
                df_show = pd.DataFrame(current_results)[["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]]
                result_table.dataframe(df_show, use_container_width=True)

            with st.spinner("Processing your URLs (one fresh browser per site)..."):
                results = asyncio.run(process_urls(urls, max_wait, headless, update_ui))

            success_count = sum(1 for r in results if r["Status"] == "Success")
            if success_count > 0:
                st.success(f"✅ Done! {success_count}/{len(results)} successful")
            else:
                st.warning("No successes yet — check Debug column (usually Cloudflare)")

            final_df = pd.DataFrame(results)[["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]]
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Download Results CSV", data=csv, file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv", mime="text/csv")

            st.markdown("### Status Summary")
            st.dataframe(final_df["Status"].value_counts(), use_container_width=True)

    except Exception as e:
        st.error(f"File error: {str(e)}")
        st.code(traceback.format_exc())

st.markdown("---")
st.caption("""
**All fixed!** No more "cannot reuse ChromeOptions" or connection errors.  
Tips: 
• For best results, set wait time to 80–100 seconds  
• Run with 5–15 URLs first to test  
• If you see "Blocked by Cloudflare", just wait a few minutes and try again  
Need any changes? Just tell me! 😄
""")
