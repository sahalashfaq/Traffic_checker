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
from selenium.common.exceptions import TimeoutException

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass
local_css("style.css")

# ── Detect Streamlit Cloud ───────────────────────────────────────────────────
is_cloud = os.environ.get("STREAMLIT_SERVER_ENABLE_STATIC_SERVING", False)

# ── Driver Factory ───────────────────────────────────────────────────────────
def create_driver(headless_mode=True):
    options = uc.ChromeOptions()
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--allow-running-insecure-content")
    
    # Current realistic UA (early 2026)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    
    if is_cloud or headless_mode:
        options.add_argument("--headless=new")
    
    status_placeholder = st.empty()
    status_placeholder.caption("Initializing browser... (auto-detect)")
    
    driver = None
    
    # Try 1: Auto-detect (recommended - no version_main)
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.implicitly_wait(10)
        if not (is_cloud or headless_mode):
            driver.maximize_window()
        status_placeholder.caption("✓ Browser ready (auto-detected version)")
        return driver
    except Exception as e:
        status_placeholder.caption(f"Auto-detect failed: {str(e)[:120]} → trying fallbacks")
    
    # Fallback versions - order most likely first (adjust if needed after seeing logs)
    fallback_versions = [130, 129, 128, 127, 126, 125, 124]
    
    for ver in fallback_versions:
        try:
            status_placeholder.caption(f"Trying Chrome major version {ver}...")
            driver = uc.Chrome(
                version_main=ver,
                options=options,
                use_subprocess=True,
            )
            driver.implicitly_wait(10)
            if not (is_cloud or headless_mode):
                driver.maximize_window()
            status_placeholder.caption(f"✓ Success with fallback version {ver}")
            return driver
        except Exception as e:
            status_placeholder.caption(f"Version {ver} failed: {str(e)[:100]}")
    
    # All attempts failed
    status_placeholder.error("❌ Browser init failed after all attempts. Check logs / try later.")
    raise RuntimeError("ChromeDriver could not be initialized")

# ── Scrape one URL ───────────────────────────────────────────────────────────
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
        
        # Cloudflare wait
        page_lower = driver.page_source.lower()
        if any(p in page_lower for p in ["cloudflare", "just a moment", "checking your browser"]):
            result["Debug"] = "Cloudflare challenge detected → waiting"
            start_cf = time.time()
            cleared = False
            while time.time() - start_cf < min(max_wait, 40):
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
            result["Debug"] += " (cleared)" if cleared else " (failed)"
            if not cleared:
                result["Status"] = "Blocked by Cloudflare"
                return result
        
        # Wait for modal
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal appeared"
        except TimeoutException:
            result["Debug"] += " | No modal (timeout)"
            result["Status"] = "Timeout"
            return result
        
        time.sleep(2.5 + random.uniform(0, 1.5))
        
        # Extraction helpers
        def safe_xpath(xpath):
            try:
                txt = driver.find_element(By.XPATH, xpath).text.strip()
                return txt if txt else "N/A"
            except:
                return "N/A"
        
        # Website Name
        ws = safe_xpath("/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p")
        if ws == "N/A":
            for s in [
                ".ReactModalPortal h2",
                ".ReactModalPortal p:first-of-type",
                "//div[contains(@class,'ReactModalPortal')]//p[1]",
            ]:
                try:
                    by = By.CSS_SELECTOR if s.startswith(".") else By.XPATH
                    ws = driver.find_element(by, s).text.strip()
                    if ws: break
                except:
                    pass
        result["Website Name"] = ws
        
        # Organic Traffic
        tr = safe_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span")
        if tr == "N/A":
            for s in [
                "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]",
                "span[class*='css-vemh4e']",
            ]:
                try:
                    by = By.XPATH if s.startswith("//") else By.CSS_SELECTOR
                    txt = driver.find_element(by, s).text.strip()
                    if txt and any(c in txt for c in "KMGB0123456789"):
                        tr = txt
                        break
                except:
                    pass
        result["Organic Traffic"] = tr
        
        # Traffic Worth
        wo = safe_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span")
        if wo == "N/A":
            for s in [
                "//span[starts-with(text(),'$')]",
                "//span[contains(text(),'$')]",
            ]:
                try:
                    by = By.XPATH
                    wo = driver.find_element(by, s).text.strip()
                    if wo and '$' in wo: break
                except:
                    pass
        result["Traffic Worth"] = wo
        
        if any(v != "N/A" for v in [ws, tr, wo]):
            result["Status"] = "Success"
            result["Debug"] += " | Values extracted"
        else:
            result["Status"] = "No data"
            result["Debug"] += " | No values found"
    
    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:150]}"
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        time.sleep(1)  # extra breathing room
    
    return result

# ── Batch processor ──────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    results = []
    total = len(urls)
    start = time.time()
    
    for i, url in enumerate(urls):
        row = await asyncio.get_event_loop().run_in_executor(
            None, scrape_ahrefs_traffic, url, max_wait, headless
        )
        results.append(row)
        
        processed = i + 1
        elapsed = time.time() - start
        eta = (elapsed / processed) * (total - processed) if processed < total else 0
        
        success = sum(1 for r in results if r["Status"] == "Success")
        
        if progress_callback:
            progress_callback(processed, total, success, round(eta / 60, 1), results)
        
        time.sleep(6 + random.uniform(0, 5))  # generous delay
    
    return results

# ── UI ───────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")
st.title("🔍 Ahrefs Traffic Bulk Checker")
st.caption("2026 • Auto + Fallback • Fresh Browser per URL • Cloud Hardened")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("Max wait per URL (sec)", 40, 200, 100, 5)
with col3:
    headless = st.checkbox("Headless mode", value=True, help="Required on Streamlit Cloud")

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("URL column", df.columns)
        raw = df[url_col].dropna().unique()
        urls = [str(u).strip() for u in raw if str(u).strip().startswith(("http", "www"))]
        st.markdown(f"**{len(urls)} URLs ready**")
        
        if st.button("Start Processing", type="primary"):
            progress = st.progress(0)
            status = st.empty()
            table = st.empty()
            
            def ui_update(curr, tot, succ, eta_min, res):
                progress.progress(curr / tot)
                status.markdown(f"**{curr}/{tot}** • Success: {succ} • ETA ~{eta_min} min")
                df_show = pd.DataFrame(res)[["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]]
                table.dataframe(df_show, use_container_width=True)
            
            with st.spinner("Processing (one browser per site)..."):
                results = asyncio.run(process_urls(urls, max_wait, headless, ui_update))
            
            succ_count = sum(1 for r in results if r["Status"] == "Success")
            if succ_count > 0:
                st.success(f"Done! {succ_count}/{len(results)} successful")
            else:
                st.warning("No successes — see Debug column (Cloudflare / version issues?)")
            
            final_df = pd.DataFrame(results)[["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]]
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv, f"ahrefs_{time.strftime('%Y%m%d_%H%M')}.csv", "text/csv")
            
            st.markdown("### Summary")
            st.dataframe(final_df["Status"].value_counts(), use_container_width=True)
    
    except Exception as e:
        st.error(f"File error: {str(e)}")
        st.code(traceback.format_exc())

st.markdown("---")
st.caption("""
Tips:
• Use 100–150 sec wait if many Cloudflare blocks
• Test with 3–8 URLs first
• If init keeps failing → look at the status messages (which version worked/failed)
• Consider adding packages.txt in repo root: chromium\nchromium-driver
""")
