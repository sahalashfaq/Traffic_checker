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

# ── Driver Factory with auto + fallback versions ─────────────────────────────
def create_driver(headless_mode=True):
    options = uc.ChromeOptions()
    
    # Essential for cloud / headless stability
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--allow-running-insecure-content")
    
    # Recent realistic user agent (helps stealth)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    
    if is_cloud or headless_mode:
        options.add_argument("--headless=new")
    
    driver = None
    error_msgs = []
    
    # Step 1: Try auto-detection (usually best)
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.implicitly_wait(10)
        if not (is_cloud or headless_mode):
            driver.maximize_window()
        st.caption("✓ Driver started (auto-detected version)")
        return driver
    except Exception as e:
        error_msgs.append(f"Auto-detect failed: {str(e)[:120]}")
    
    # Step 2: Try recent major versions in order (most likely → older)
    fallback_versions = [130, 129, 128, 127, 126, 125, 124]
    
    for ver in fallback_versions:
        try:
            driver = uc.Chrome(
                version_main=ver,
                options=options,
                use_subprocess=True,
            )
            driver.implicitly_wait(10)
            if not (is_cloud or headless_mode):
                driver.maximize_window()
            st.caption(f"✓ Driver started using fallback Chrome major version {ver}")
            return driver
        except Exception as e:
            error_msgs.append(f"Version {ver} failed: {str(e)[:100]}")
    
    # If everything failed → show all attempts
    st.error("❌ Could not start ChromeDriver after multiple attempts")
    for msg in error_msgs:
        st.caption(msg)
    raise RuntimeError("ChromeDriver initialization failed after all attempts")

# ── Scraping function ────────────────────────────────────────────────────────
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
        time.sleep(2.5 + random.uniform(0, 1.8))
        
        # Cloudflare check & wait
        page_source_lower = driver.page_source.lower()
        if any(phrase in page_source_lower for phrase in ["cloudflare", "just a moment", "checking your browser"]):
            result["Debug"] = "Cloudflare → waiting up to 35s"
            start = time.time()
            cleared = False
            while time.time() - start < min(max_wait, 35):
                try:
                    if any(c['name'] == 'cf_clearance' for c in driver.get_cookies()):
                        cleared = True
                        break
                    if "cloudflare" not in driver.page_source.lower():
                        cleared = True
                        break
                except:
                    pass
                time.sleep(1.6)
            result["Debug"] += " (cleared)" if cleared else " (NOT cleared)"
            if not cleared:
                result["Status"] = "Blocked by Cloudflare"
                return result
        
        # Wait for results modal
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal found"
        except TimeoutException:
            result["Debug"] += " | Modal NOT found"
            result["Status"] = "Timeout - no modal"
            return result
        
        time.sleep(2.2 + random.uniform(0, 1.8))
        
        # ── Extraction helpers ───────────────────────────────────────────────
        def safe_text_xpath(xpath):
            try:
                txt = driver.find_element(By.XPATH, xpath).text.strip()
                return txt if txt else "N/A"
            except:
                return "N/A"
        
        # Website name
        website = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p")
        if website == "N/A":
            for sel_type, sel_val in [
                (By.CSS_SELECTOR, ".ReactModalPortal h2"),
                (By.CSS_SELECTOR, ".ReactModalPortal p:first-of-type"),
                (By.XPATH, "//div[contains(@class,'ReactModalPortal')]//p[1]"),
            ]:
                try:
                    website = driver.find_element(sel_type, sel_val).text.strip()
                    if website:
                        break
                except:
                    continue
        result["Website Name"] = website
        
        # Organic traffic
        traffic = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span")
        if traffic == "N/A":
            for sel_type, sel_val in [
                (By.XPATH, "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"),
                (By.CSS_SELECTOR, "span[class*='css-vemh4e']"),
            ]:
                try:
                    txt = driver.find_element(sel_type, sel_val).text.strip()
                    if txt and any(c in txt for c in "KMGB0123456789"):
                        traffic = txt
                        break
                except:
                    continue
        result["Organic Traffic"] = traffic
        
        # Traffic worth
        worth = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span")
        if worth == "N/A":
            for sel_type, sel_val in [
                (By.XPATH, "//span[starts-with(text(),'$')]"),
                (By.XPATH, "//span[contains(text(),'$')]"),
            ]:
                try:
                    worth = driver.find_element(sel_type, sel_val).text.strip()
                    if worth and '$' in worth:
                        break
                except:
                    continue
        result["Traffic Worth"] = worth
        
        # Determine final status
        if any(v != "N/A" for v in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]]):
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data found"
            result["Debug"] += " | Modal appeared but no values"
    
    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:180]}"
    
    finally:
        if driver is not None:
            try:
                driver.quit()
            except:
                pass
        time.sleep(0.7)  # breathing room after quit
    
    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    results = []
    total = len(urls)
    start_time = time.time()
    
    for i, url in enumerate(urls):
        row = await asyncio.get_event_loop().run_in_executor(
            None, scrape_ahrefs_traffic, url, max_wait, headless
        )
        results.append(row)
        
        processed = i + 1
        elapsed = time.time() - start_time
        eta_sec = (elapsed / processed) * (total - processed) if processed < total else 0
        
        success_count = sum(1 for r in results if r["Status"] == "Success")
        
        if progress_callback:
            progress_callback(processed, total, success_count, round(eta_sec / 60, 1), results)
        
        # Human-like delay between sessions
        time.sleep(5 + random.uniform(0, 4))
    
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")
st.title("🔍 Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 • Auto + Fallback Chrome • Per-URL Browser • Cloud Stable")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("📁 Upload CSV / XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("⏱ Max wait per site (seconds)", 30, 180, 90, step=5)
with col3:
    headless = st.checkbox("🤖 Headless mode", value=True,
                          help="Keep checked on Streamlit Cloud")

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        url_col = st.selectbox("Select column with URLs", df.columns)
        raw_urls = df[url_col].dropna().unique()
        urls = [str(u).strip() for u in raw_urls if str(u).strip().startswith(("http", "www."))]
        
        st.markdown(f"**Found {len(urls)} valid-looking URLs**")
        
        if st.button("▶️ Start Processing", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_table = st.empty()
            
            def update_ui(curr, tot, succ, eta_min, curr_results):
                progress_bar.progress(curr / tot)
                status_text.markdown(
                    f"**Progress:** {curr}/{tot} • **Success:** {succ} • **ETA:** ~{eta_min} min"
                )
                df_view = pd.DataFrame(curr_results)[
                    ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                ]
                results_table.dataframe(df_view, use_container_width=True)
            
            with st.spinner("Processing (new browser instance per URL)..."):
                results = asyncio.run(
                    process_urls(urls, max_wait, headless, update_ui)
                )
            
            success_count = sum(1 for r in results if r["Status"] == "Success")
            
            if success_count > 0:
                st.success(f"Finished — {success_count}/{len(results)} successful")
            else:
                st.warning("No successful extractions — check Debug column")
            
            final_df = pd.DataFrame(results)[
                ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
            ]
            
            csv_bytes = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Download Results as CSV",
                data=csv_bytes,
                file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            
            st.markdown("### Status Summary")
            st.dataframe(final_df["Status"].value_counts(), use_container_width=True)
    
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())

st.markdown("---")
st.caption("""
Tips:
• Try 80–120 seconds wait time if you see many Cloudflare blocks
• Start with 5–10 URLs to test stability
• If still failing → look at the version error messages in UI
""")
