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
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ── Detect Streamlit Cloud ──────────────────────────────────────────────────
is_cloud = os.environ.get("STREAMLIT_SERVER_ENABLE_STATIC_SERVING", False)

# ── Driver Factory ───────────────────────────────────────────────────────────
@st.cache_resource
def init_driver(headless_mode=True):
    options = uc.ChromeOptions()
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    
    # Modern realistic user-agent (2025–2026)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    
    if is_cloud or headless_mode:
        options.add_argument("--headless=new")
        st.info("Headless mode active (required on Streamlit Cloud)")
    else:
        st.info("Visible browser mode (good for local debugging)")
    
    try:
        driver = uc.Chrome(
            version_main=131,           # update this every few months
            options=options,
            use_subprocess=True
        )
        driver.implicitly_wait(12)
        if not (is_cloud or headless_mode):
            driver.maximize_window()
        st.success("Browser initialized")
        return driver
    except Exception as e:
        st.error(f"Browser init failed: {str(e)}")
        st.stop()

# ── Human-like helper actions ───────────────────────────────────────────────
def human_like_delay(driver, min_sec=0.8, max_sec=2.3):
    time.sleep(random.uniform(min_sec, max_sec))

def simulate_human_interaction(driver):
    try:
        actions = ActionChains(driver)
        # tiny random scroll
        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.15);")
        human_like_delay(driver, 0.4, 1.1)
        # fake mouse movement
        actions.move_by_offset(random.randint(30, 180), random.randint(20, 120)).perform()
        human_like_delay(driver, 0.6, 1.4)
    except:
        pass

# ── Core scraping function (2026 edition) ────────────────────────────────────
def scrape_ahrefs_traffic(driver, url, max_wait=90):
    result = {
        "URL": url,
        "Website Name": "N/A",
        "Organic Traffic": "N/A",
        "Traffic Worth": "N/A",
        "Status": "Failed",
        "Debug": ""
    }

    try:
        clean_url = url.strip().rstrip('/').lower()
        if not clean_url.startswith('http'):
            clean_url = 'https://' + clean_url
        query_url = f"https://ahrefs.com/traffic-checker/?input={clean_url}&mode=subdomains"
        
        driver.get(query_url)
        human_like_delay(driver, 2.2, 4.0)

        # ── Cloudflare / antibot detection ───────────────────────────────
        start_cf = time.time()
        cf_cleared = False
        while time.time() - start_cf < min(max_wait, 45):
            page_lower = driver.page_source.lower()
            if any(phrase in page_lower for phrase in ["just a moment", "cloudflare", "checking your browser", "cf-ray", "cf-browser-verification"]):
                result["Debug"] += "Cloudflare → waiting | "
                time.sleep(1.8)
                continue
            
            # success criteria
            cookies = driver.get_cookies()
            cf_cookie = any(c['name'] == 'cf_clearance' for c in cookies)
            no_cf_text = all(p not in page_lower for p in ["cloudflare", "just a moment"])
            
            if cf_cookie or no_cf_text:
                cf_cleared = True
                result["Debug"] += "Cloudflare passed | "
                break
            time.sleep(1.5)

        if not cf_cleared:
            result["Status"] = "Blocked by Cloudflare"
            result["Debug"] += "CF clearance failed"
            return result

        # ── Wait for main result container ───────────────────────────────
        selectors_modal = [
            ".ReactModalPortal",
            "[role='dialog']",
            "[class*='modal']",
            "[class*='Overlay']",
            "[class*='traffic-checker-result']",
            "[data-testid*='result']",
        ]

        found_container = False
        for sel in selectors_modal:
            try:
                WebDriverWait(driver, 18).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                found_container = True
                result["Debug"] += f"Container ({sel}) found | "
                break
            except:
                continue

        if not found_container:
            # last chance — look for numbers directly
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'K') or contains(text(),'M') or contains(text(),'$')]"))
                )
                result["Debug"] += "Found numbers without modal | "
            except:
                result["Status"] = "No result container"
                result["Debug"] += "No modal or numbers detected"
                return result

        # Extra render time + fake human behavior
        simulate_human_interaction(driver)
        time.sleep(random.uniform(2.8, 5.2))

        # ── Extraction strategies ─────────────────────────────────────────
        def extract_by_patterns():
            data = {"Website Name": "N/A", "Organic Traffic": "N/A", "Traffic Worth": "N/A"}

            # 1. Domain / name (usually biggest text or first heading-like)
            for pattern in [
                "//h1 | //h2 | //*[contains(@class,'domain') or contains(@class,'title') or contains(@class,'header')]",
                ".ReactModalPortal h1, .ReactModalPortal h2, .ReactModalPortal strong",
                "p, div > strong, [class*='domain']"
            ]:
                try:
                    els = driver.find_elements(By.XPATH, pattern)
                    for el in els:
                        t = el.text.strip()
                        if len(t) > 5 and '.' in t and not any(c.isdigit() for c in t[:6]) and '$' not in t:
                            data["Website Name"] = t
                            break
                    if data["Website Name"] != "N/A":
                        break
                except:
                    pass

            # 2. Organic traffic — big number with K/M/B usually near "organic" or "search"
            traffic_texts = driver.find_elements(By.XPATH,
                "//*[contains(translate(text(),'KM','km'),'k') or contains(translate(text(),'KM','km'),'m') or contains(text(),'visits') or contains(text(),'traffic')]"
            )
            for el in traffic_texts:
                txt = el.text.strip()
                if any(u in txt.lower() for u in ['k', 'm', ' visits', ' traffic', 'search']):
                    parent_html = el.find_element(By.XPATH, "..").get_attribute("outerHTML").lower()
                    if any(w in parent_html for w in ['organic', 'search', 'visits']):
                        data["Organic Traffic"] = txt
                        break
            if data["Organic Traffic"] == "N/A" and traffic_texts:
                data["Organic Traffic"] = traffic_texts[0].text.strip()  # best guess

            # 3. Traffic value ($)
            money_els = driver.find_elements(By.XPATH, "//*[contains(text(),'$')]")
            for el in money_els:
                txt = el.text.strip()
                if txt.startswith('$') and any(c.isdigit() for c in txt[1:]):
                    context = el.find_element(By.XPATH, "..").text.lower()
                    if any(w in context for w in ['worth', 'value', 'traffic value', 'usd']):
                        data["Traffic Worth"] = txt
                        break
            if data["Traffic Worth"] == "N/A" and money_els:
                data["Traffic Worth"] = money_els[0].text.strip()  # fallback

            return data

        extracted = extract_by_patterns()

        result.update(extracted)

        # Decide final status
        meaningful_data = sum(1 for v in extracted.values() if v != "N/A")
        if meaningful_data >= 1:
            result["Status"] = "Success"
            result["Debug"] += "Data extracted ✓"
        else:
            result["Status"] = "No usable data"
            result["Debug"] += "Container found but no parseable values"

    except Exception as e:
        result["Status"] = "Exception"
        result["Debug"] = f"Error: {str(e)[:180]}…"

    return result

# ── Batch processor ──────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    driver = init_driver(headless_mode=headless)
    results = []
    total = len(urls)

    for i, url in enumerate(urls, 1):
        row = scrape_ahrefs_traffic(driver, url, max_wait)
        results.append(row)

        elapsed = time.time() - st.session_state.get('start_time', time.time())
        eta = (elapsed / i) * (total - i) if i < total else 0

        success = sum(1 for r in results if r["Status"] == "Success")

        if progress_callback:
            progress_callback(i, total, success, round(eta / 60, 1), results)

        time.sleep(random.uniform(3.5, 7.0))  # polite delay

    driver.quit()
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker 2026", layout="wide")

st.title("🔍 Ahrefs Traffic Checker – Bulk (2026 edition)")
st.caption("Improved Cloudflare bypass • Flexible selectors • Human-like behavior")

col1, col2, col3 = st.columns([4, 2, 2])

with col1:
    uploaded_file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

with col2:
    max_wait = st.number_input("Max wait per site (seconds)", 40, 180, 75, step=5)

with col3:
    headless = st.checkbox("Headless mode", value=True,
                          help="Must be ON when running on Streamlit Cloud")

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        url_col = st.selectbox("Select column containing URLs", df.columns)
        raw_urls = df[url_col].dropna().astype(str).tolist()
        urls = [u.strip() for u in raw_urls if u.strip() and len(u.strip()) > 5]
        urls = list(dict.fromkeys(urls))  # remove duplicates
        
        st.success(f"Found **{len(urls)}** unique URLs")

        if st.button("▶️  Start Extraction", type="primary", use_container_width=True):
            if 'start_time' not in st.session_state:
                st.session_state.start_time = time.time()

            progress_bar = st.progress(0)
            status_text = st.empty()
            result_table = st.empty()

            def update_progress(current, total, success, eta_min, current_results):
                progress_bar.progress(current / total)
                status_text.markdown(
                    f"**Progress:** {current}/{total} • **Success:** {success} • **ETA:** ~{eta_min:.1f} min"
                )
                df_show = pd.DataFrame(current_results)
                cols = ["URL", "Website Name", "Organic Traffic", "Traffic Worth", "Status", "Debug"]
                result_table.dataframe(df_show[cols], use_container_width=True, hide_index=True)

            with st.spinner("Processing... (this can take several minutes)"):
                results = asyncio.run(
                    process_urls(
                        urls,
                        max_wait=max_wait,
                        headless=headless,
                        progress_callback=update_progress
                    )
                )

            st.session_state.pop('start_time', None)

            final_df = pd.DataFrame(results)
            success_count = (final_df["Status"] == "Success").sum()

            if success_count > 0:
                st.success(f"Finished — {success_count}/{len(results)} successful")
            else:
                st.error("No successful extractions. Most likely blocked by Cloudflare.")

            csv_bytes = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Download Results (CSV)",
                data=csv_bytes,
                file_name=f"ahrefs_traffic_{time.strftime('%Y-%m-%d_%H%M')}.csv",
                mime="text/csv"
            )

            st.subheader("Summary")
            st.dataframe(final_df["Status"].value_counts().to_frame(), use_container_width=True)

    except Exception as e:
        st.error(f"File reading error: {str(e)}")
        st.code(traceback.format_exc())

st.markdown("---")
st.caption("""
**Tips 2026**
• Cloudflare is the #1 blocker — residential proxies or paid APIs are often the only stable solution
• Increase delay / max_wait if many "Blocked by Cloudflare"
• Ahrefs free checker sometimes returns almost nothing without login
• Consider official Ahrefs API or third-party wrappers (RapidAPI, etc.)
""")
