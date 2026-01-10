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

# ── Driver Factory (same reliable approach as Facebook Email Extractor) ─────
@st.cache_resource
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Very important for Debian Bookworm / Streamlit Cloud
    chrome_options.binary_location = "/usr/bin/chromium"
    
    service = Service(executable_path="/usr/bin/chromedriver")
    
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error("Failed to initialize Chromium driver")
        st.error(str(e))
        st.error("Make sure packages.txt contains exactly:")
        st.code("chromium\nchromium-driver", language="text")
        st.stop()

# ── Single URL scraping function ─────────────────────────────────────────────
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
        ahrefs_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(ahrefs_url)

        # Give Cloudflare some initial breathing room
        time.sleep(6)

        # Wait for clearance cookie (best effort in headless)
        start_cf = time.time()
        while time.time() - start_cf < max_wait:
            cookies = driver.get_cookies()
            if any(c.get('name') == 'cf_clearance' for c in cookies):
                break
            time.sleep(1.8)

        # Wait for the results modal
        WebDriverWait(driver, max_wait - 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(selector):
            try:
                return modal.find_element(By.CSS_SELECTOR, selector).text.strip()
            except:
                return "N/A"

        result.update({
            "Website": safe_text("h2") or "N/A",
            "Organic Traffic": safe_text("span.css-vemh4e") or "N/A",
            "Traffic Value": safe_text("span.css-6s0ffe") or "N/A",
            "Status": "Success"
        })

        # Top Country
        country_row = safe_text("table:nth-of-type(1) tbody tr:first-child")
        if country_row != "N/A":
            match = re.match(r"(.+?)\s+([\d.%]+)", country_row)
            if match:
                result["Top Country"] = match.group(1).strip()
                result["Top Country Share"] = match.group(2)

        # Top Keyword
        keyword_row = safe_text("table:nth-of-type(2) tbody tr:first-child")
        if keyword_row != "N/A":
            match = re.match(r"(.+?)\s+(\d+)\s+([\d,K,M\.]+)", keyword_row)
            if match:
                result["Top Keyword"] = match.group(1)
                result["Keyword Position"] = match.group(2)
                result["Top Keyword Traffic"] = match.group(3)

    except Exception as e:
        result["Organic Traffic"] = f"Failed ({str(e)[:60]}...)"
        result["Status"] = "Failed"

    return result

# ── Async batch processor ────────────────────────────────────────────────────
async def process_all_urls(urls, max_wait, progress_callback=None):
    driver = init_driver()
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    results = []
    total = len(urls)
    start_time = time.time()

    for i, url in enumerate(urls):
        row = await loop.run_in_executor(executor, scrape_ahrefs_traffic, driver, url, max_wait)
        results.append(row)

        elapsed = time.time() - start_time
        eta_sec = (elapsed / (i+1)) * (total - i - 1) if i < total-1 else 0
        eta_min = round(eta_sec / 60, 1)

        success_count = sum(1 for r in results if r["Status"] == "Success")

        if progress_callback:
            progress_callback(i+1, total, success_count, eta_min, results)

    driver.quit()
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Bulk Traffic Checker", layout="centered")

st.title("Ahrefs Traffic Checker (Bulk)")
st.caption("Cloud-compatible version • Many requests may fail due to Cloudflare")

uploaded_file = st.file_uploader("Upload CSV or XLSX file", type=["csv", "xlsx"])

max_wait = st.number_input(
    "Maximum wait time per URL (seconds)",
    min_value=30, max_value=180, value=70, step=5
)

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_column = st.selectbox("Select column with URLs", df.columns)
        urls = df[url_column].dropna().unique().tolist()

        st.markdown(f"**Found {len(urls)} unique URLs**")

        if st.button("Start Processing", type="primary"):
            spinner = st.empty()
            spinner.markdown(
                """
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="loader"></div>
                    <span>Initializing & Processing...</span>
                </div>
                <style>
                .loader {
                    border: 5px solid #f3f3f3;
                    border-top: 5px solid #3498db;
                    border-radius: 50%;
                    width: 28px;
                    height: 28px;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
                """, unsafe_allow_html=True
            )

            progress_bar = st.progress(0)
            status_text = st.empty()
            result_table = st.empty()

            def update_ui(scraped, total, success, eta, current_results):
                progress_bar.progress(scraped / total)
                status_text.markdown(
                    f"**Progress:** {scraped}/{total} • **Success:** {success} • **ETA:** ~{eta:.1f} min"
                )
                result_table.dataframe(pd.DataFrame(current_results))

            results = asyncio.run(
                process_all_urls(urls, max_wait, update_ui)
            )

            spinner.empty()
            st.success("Processing completed!")

            if results:
                final_df = pd.DataFrame(results)
                csv_buffer = final_df.to_csv(index=False).encode('utf-8')

                st.download_button(
                    label="Download Results CSV",
                    data=csv_buffer,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

            st.markdown("---")
            st.caption("**Note:** Due to aggressive Cloudflare protection on cloud IPs, expect many failed requests. This is normal behavior.")

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")

st.markdown("**Deployment files reminder**")
with st.expander("Required deployment files"):
    st.code("""# packages.txt
chromium
chromium-driver""", language="text")

    st.code("""# requirements.txt
streamlit
pandas
openpyxl
selenium""", language="text")
