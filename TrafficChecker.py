import streamlit as st
import pandas as pd
import re
import asyncio
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ----------------- Driver Setup (exactly like your working Facebook scraper) --------------------
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Use Chromium binary explicitly (important!)
    chrome_options.binary_location = "/usr/bin/chromium"

    service = Service(executable_path="/usr/bin/chromedriver")
    
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        st.success("Chromium + chromedriver initialized successfully (Streamlit Cloud native)")
        return driver
    except Exception as e:
        st.error(f"Driver failed: {str(e)}")
        st.error("Check build log → make sure packages.txt contains ONLY: chromium + chromium-driver")
        st.stop()

# ----------------- Scraper Logic (improved Cloudflare handling) --------------------
def scrape_ahrefs_from_url(driver, url, max_wait_time):
    ahrefs_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
    result = {
        "URL": url,
        "Website": "Error",
        "Website Traffic": "Error",
        "Traffic Value": "N/A",
        "Top Country": "N/A",
        "Top Country Share": "N/A",
        "Top Keyword": "N/A",
        "Keyword Position": "N/A",
        "Top Keyword Traffic": "N/A",
    }

    try:
        driver.get(ahrefs_url)
        time.sleep(7)  # initial wait

        # Wait for possible cf_clearance cookie (best-effort in headless)
        start = time.time()
        while time.time() - start < max_wait_time:
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            if 'cf_clearance' in cookies:
                break
            time.sleep(2.5)

        WebDriverWait(driver, max_wait_time - 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(css):
            try:
                return modal.find_element(By.CSS_SELECTOR, css).text.strip()
            except:
                return "N/A"

        result.update({
            "Website": safe_text("h2") or "N/A",
            "Website Traffic": safe_text("span.css-vemh4e") or "N/A",
            "Traffic Value": safe_text("span.css-6s0ffe") or "N/A",
        })

        # Top Country
        country_raw = safe_text("table:nth-of-type(1) tbody tr:first-child")
        if country_raw != "N/A":
            m = re.match(r"(.+?)\s+([\d\.%]+)", country_raw.strip())
            if m:
                result["Top Country"] = m.group(1).strip()
                result["Top Country Share"] = m.group(2)

        # Top Keyword
        kw_raw = safe_text("table:nth-of-type(2) tbody tr:first-child")
        if kw_raw != "N/A":
            m = re.match(r"(.+?)\s+(\d+)\s+([\dKM,.]+)", kw_raw.strip())
            if m:
                result["Top Keyword"] = m.group(1)
                result["Keyword Position"] = m.group(2)
                result["Top Keyword Traffic"] = m.group(3)

    except Exception as e:
        result["Website Traffic"] = f"Failed ({str(e)[:70]})"

    return result

# ----------------- Async Runner --------------------
async def run_scraper_async(urls, max_wait_time, spinner_placeholder):
    driver = get_driver()
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=3)

    start_time = time.time()
    results = []
    total = len(urls)

    for i, url in enumerate(urls):
        row = await loop.run_in_executor(executor, scrape_ahrefs_from_url, driver, url, max_wait_time)
        results.append(row)

        elapsed = time.time() - start_time
        est_sec = (elapsed / (i+1)) * (total - i - 1) if i < total-1 else 0
        est_min = round(est_sec / 60, 1)

        if i == 0:
            spinner_placeholder.empty()

        yield {
            "progress": (i + 1) / total,
            "scraped": i + 1,
            "success": sum(1 for r in results if "Error" not in r["Website Traffic"] and "Failed" not in r["Website Traffic"]),
            "estimated_time": f"{est_min} min",
            "current_data": results[:],
        }

    driver.quit()

# ----------------- UI (same style as Facebook extractor) --------------------
st.set_page_config(layout="centered", page_title="Ahrefs Traffic Batch Checker")

uploaded_file = st.file_uploader("Upload CSV/XLSX with URLs", type=["csv", "xlsx"])
max_wait_time = st.number_input("Max wait per URL (seconds)", min_value=30, max_value=300, value=60, step=5)

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_column = st.selectbox("Select URL column", df.columns)
        urls = df[url_column].dropna().unique().tolist()
    except Exception as e:
        st.error(f"File processing error: {e}")
        st.stop()

    if st.button("Start Processing"):
        # Countdown spinner
        spinner1 = st.empty()
        for i in range(5, 0, -1):
            spinner1.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:10px;">
                    <div class="loader"></div>
                    <p>Starting in {i} seconds...</p>
                </div>
                <style>
                .loader {{border:6px solid #f3f3f3;border-top:6px solid #3498db;border-radius:50%;width:30px;height:30px;animation:spin 1s linear infinite;}}
                @keyframes spin {{0% {{transform:rotate(0deg)}} 100% {{transform:rotate(360deg)}}}}
                </style>
                """, unsafe_allow_html=True
            )
            time.sleep(1)
        spinner1.empty()

        # Processing spinner
        spinner2 = st.empty()
        spinner2.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;">
                <div class="loader"></div>
                <p>Processing URLs...</p>
            </div>
            <style>.loader {{border:6px solid #f3f3f3;border-top:6px solid #3498db;border-radius:50%;width:30px;height:30px;animation:spin 1s linear infinite;}}</style>
            """, unsafe_allow_html=True
        )

        progress_bar = st.progress(0)
        status = st.empty()
        table = st.empty()

        async def run_and_show():
            start = time.time()
            async for update in run_scraper_async(urls, max_wait_time, spinner1):
                progress_bar.progress(update["progress"])
                status.markdown(
                    f"**Progress:** {update['scraped']}/{len(urls)}\n"
                    f"**Success:** {update['success']}\n"
                    f"**ETA:** {update['estimated_time']}"
                )
                table.dataframe(pd.DataFrame(update["current_data"]))

            spinner2.empty()
            st.success(f"Completed in {round(time.time() - start, 1)} seconds!")

            final_df = pd.DataFrame(update["current_data"])
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Results", csv, "ahrefs_traffic_results.csv", "text/csv")

        asyncio.run(run_and_show())

st.markdown("**Important 2026 note:** Ahrefs has very strong Cloudflare protection. From cloud IPs (like Streamlit) many requests will fail or show 0 traffic. This is normal behavior — not a code issue. For better results use residential proxies or official API.")
