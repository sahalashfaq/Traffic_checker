# main.py
import streamlit as st
import pandas as pd
import re
import time
import asyncio
import os
import traceback
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

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
@st.cache_resource(ttl="10m")  # cache short time — still helps a bit with repeated init
def get_driver_options(headless_mode=True):
    options = uc.ChromeOptions()
    
    # Essential for cloud/headless
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Additional stealth
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
    
    return options

def init_driver(headless_mode=True):
    options = get_driver_options(headless_mode)
    try:
        driver = uc.Chrome(
            version_main=126,  # slightly older = often more stable in containers
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

# ── Helper: Check if driver is still alive ───────────────────────────────────
def is_driver_alive(driver):
    try:
        _ = driver.title
        return True
    except (WebDriverException, Exception):
        return False

# ── Scraping function (now expects its own fresh driver) ─────────────────────
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
        driver = init_driver(headless_mode=headless)
        st.write(f"→ New browser session started for {url}")

        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)
        time.sleep(2.5 + random.uniform(0, 1.5))

        # Cloudflare detection & wait
        page_source = driver.page_source.lower()
        if any(x in page_source for x in ["cloudflare", "just a moment", "checking your browser"]):
            result["Debug"] = "Cloudflare challenge → waiting up to 35s..."
            start_cf = time.time()
            cleared = False
            while time.time() - start_cf < min(max_wait, 35):
                try:
                    cookies = driver.get_cookies()
                    if any(c.get('name') == 'cf_clearance' for c in cookies):
                        cleared = True
                        break
                    if "cloudflare" not in driver.page_source.lower():
                        cleared = True
                        break
                except:
                    pass
                time.sleep(1.8)
            if cleared:
                result["Debug"] += " cleared"
            else:
                result["Debug"] += " → NOT cleared"
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

        # ── Extraction helpers ───────────────────────────────────────────────
        def safe_text_xpath(xpath):
            try:
                el = driver.find_element(By.XPATH, xpath)
                txt = el.text.strip()
                return txt if txt else "N/A"
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
                    continue
        result["Website Name"] = website

        # Organic Traffic
        traffic = safe_text_xpath("/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span")
        if traffic == "N/A":
            for sel in [
                (By.XPATH, "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"),
                (By.CSS_SELECTOR, "span[class*='css-vemh4e']"),
            ]:
                try:
                    traffic = driver.find_element(*sel).text.strip()
                    if traffic and any(c in traffic for c in 'KMGB0123456789'):
                        break
                except:
                    continue
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
                    continue
        result["Traffic Worth"] = worth

        # Final status
        if any(v != "N/A" for v in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]]):
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data"
            result["Debug"] += " | Found modal but no values"

    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:180]}"
        if "Max retries" in str(e) or "connection refused" in str(e).lower():
            result["Debug"] += " (driver died mid-session)"

    finally:
        if driver is not None:
            try:
                driver.quit()
            except:
                pass
            time.sleep(0.6)  # give container some breathing room

    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    loop = asyncio.get_event_loop()
    results = []
    total = len(urls)
    start_time = time.time()

    for i, url in enumerate(urls):
        # Run scrape in executor (keeps streamlit responsive)
        row = await loop.run_in_executor(None, scrape_ahrefs_traffic, url, max_wait, headless)
        results.append(row)

        elapsed = time.time() - start_time
        processed = i + 1
        eta = (elapsed / processed) * (total - processed) if processed < total else 0

        success = sum(1 for r in results if r["Status"] == "Success")
        if progress_callback:
            progress_callback(processed, total, success, round(eta/60, 1), results)

        # Human-like delay between full browser sessions
        time.sleep(4 + random.uniform(0, 3.5))

    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")
st.title("🔍 Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 • Per-URL Driver • Cloudflare Hardened • Stable Cloud Mode")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("📁 Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("⏱️ Max wait per URL (sec)", 30, 180, 80, 5)
with col3:
    headless = st.checkbox("🤖 Run Headless", value=True,
                          help="Must be ON for Streamlit Cloud")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL column", df.columns)
        urls = [str(u).strip() for u in df[url_col].dropna().unique() if str(u).strip().startswith(("http", "www"))]
        st.markdown(f"**Found {len(urls)} unique URLs**")

        if st.button("▶️ Start Processing", type="primary"):
            progress = st.progress(0)
            status_text = st.empty()
            result_table = st.empty()

            def update_ui(current, total, success_count, eta_min, current_results):
                progress.progress(current / total)
                status_text.markdown(
                    f"**Progress:** {current}/{total} • **✓ Success:** {success_count} • **ETA:** ~{eta_min} min"
                )
                df_show = pd.DataFrame(current_results)[
                    ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                ]
                result_table.dataframe(df_show, use_container_width=True)

            with st.spinner("Processing URLs one by one (new browser each time)..."):
                results = asyncio.run(
                    process_urls(urls, max_wait, headless, update_ui)
                )

            success_count = sum(1 for r in results if r["Status"] == "Success")
            blocked = sum(1 for r in results if "Cloudflare" in r["Status"] or "blocked" in r["Debug"].lower())

            if success_count > 0:
                st.success(f"Finished! {success_count}/{len(results)} successful")
            else:
                st.error(f"No successes. {blocked} likely blocked by Cloudflare / resource limits.")

            if results:
                final_df = pd.DataFrame(results)[
                    ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                ]
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "⬇️ Download Results CSV",
                    data=csv,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

                st.markdown("### Status Summary")
                st.dataframe(final_df["Status"].value_counts(), use_container_width=True)

    except Exception as e:
        st.error(f"File reading error: {str(e)}")
        st.code(traceback.format_exc())

st.markdown("---")
st.caption("""
Troubleshooting tips:
• Connection refused / Max retries → fixed by per-URL driver
• Still many Cloudflare blocks → increase max wait to 100–120s or try off-peak hours
• No data even when modal appears → selectors may need updating (Ahrefs changes UI sometimes)
""")
