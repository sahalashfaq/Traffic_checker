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
from webdriver_manager.chrome import ChromeDriverManager
from io import BytesIO

# ----------------- Custom CSS Loader --------------------
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ----------------- Create Driver (automatic & compatible with Streamlit Cloud) --------------------
@st.cache_resource
def get_driver():
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        # Auto install matching chromedriver + use installed google-chrome
        service = Service(ChromeDriverManager().install())

        driver = webdriver.Chrome(service=service, options=chrome_options)
        st.success("Chrome + matching ChromeDriver initialized successfully!")
        return driver
    except Exception as e:
        st.error(f"Driver initialization failed: {str(e)}")
        st.error("Most common reasons: Chrome not installed or version mismatch.")
        st.stop()

# ----------------- Scraper Logic --------------------
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

        # Give Cloudflare time (passive)
        time.sleep(6)

        start_cf = time.time()
        while time.time() - start_cf < max_wait_time:
            if "cf_clearance" in [c['name'] for c in driver.get_cookies()]:
                break
            time.sleep(2)

        # Wait for modal
        WebDriverWait(driver, max_wait_time).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(sel):
            try:
                return modal.find_element(By.CSS_SELECTOR, sel).text.strip()
            except:
                return "N/A"

        result["Website"] = safe_text("h2") or "N/A"
        result["Website Traffic"] = safe_text("span.css-vemh4e") or "N/A"
        result["Traffic Value"] = safe_text("span.css-6s0ffe") or "N/A"

        country_raw = safe_text("table:nth-of-type(1) tbody tr:first-child")
        if country_raw != "N/A":
            m = re.match(r"(.+?)\s+([\d\.%]+)", country_raw)
            if m:
                result["Top Country"] = m.group(1).strip()
                result["Top Country Share"] = m.group(2)

        keyword_raw = safe_text("table:nth-of-type(2) tbody tr:first-child")
        if keyword_raw != "N/A":
            m = re.match(r"(.+?)\s+(\d+)\s+([\dKM\.]+)", keyword_raw)
            if m:
                result["Top Keyword"] = m.group(1)
                result["Keyword Position"] = m.group(2)
                result["Top Keyword Traffic"] = m.group(3)

    except Exception as e:
        result["Website Traffic"] = f"Failed - {str(e)[:80]}"

    return result

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
        est_sec = (elapsed / (i + 1)) * (total - i - 1) if i < total - 1 else 0
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

# ── UI ───────────────────────────────────────────────────────────────────────
st.set_page_config(layout="centered", page_title="Ahrefs Traffic Checker")

uploaded_file = st.file_uploader("Upload CSV/XLSX with URLs", type=["csv", "xlsx"])
max_wait_time = st.number_input("Max wait time per URL (sec)", 30, 300, 60, 5)

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("URL Column", df.columns)
        urls = df[url_col].dropna().unique().tolist()
    except Exception as e:
        st.error(f"File error: {e}")
        st.stop()

    if st.button("Start Processing"):
        # First spinner (countdown)
        spinner1 = st.empty()
        for i in range(5, 0, -1):
            spinner1.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;"><div class="loader"></div>Starting in {i}...</div>'
                '<style>.loader{{border:5px solid #f3f3f3;border-top:5px solid #3498db;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;}}@keyframes spin{{0%{{transform:rotate(0deg)}}100%{{transform:rotate(360deg)}}}}</style>',
                unsafe_allow_html=True
            )
            time.sleep(1)
        spinner1.empty()

        # Second spinner
        spinner2 = st.empty()
        spinner2.markdown(
            '<div style="display:flex;align-items:center;gap:12px;"><div class="loader"></div>Scraping in progress...</div>'
            '<style>.loader{{border:5px solid #f3f3f3;border-top:5px solid #3498db;border-radius:50%;width:28px;height:28px;animation:spin 1s linear infinite;}}</style>',
            unsafe_allow_html=True
        )

        progress = st.progress(0)
        status = st.empty()
        table = st.empty()

        async def process():
            start = time.time()
            async for upd in run_scraper_async(urls, max_wait_time, spinner1):
                progress.progress(upd["progress"])
                status.markdown(
                    f"**Progress:** {upd['scraped']}/{len(urls)}\n"
                    f"**Success:** {upd['success']}\n"
                    f"**ETA:** {upd['estimated_time']}"
                )
                table.dataframe(pd.DataFrame(upd["current_data"]))

            spinner2.empty()
            st.success(f"Finished in {round(time.time()-start,1)} seconds!")

            final_df = pd.DataFrame(upd["current_data"])
            csv = final_df.to_csv(index=False).encode()
            st.download_button("Download Results", csv, "ahrefs_traffic.csv", "text/csv")

        asyncio.run(process())

st.markdown("**Note 2026:** Ahrefs + Cloudflare is very aggressive against cloud IPs. Expect many failures. Consider proxies or official API if this is production use.")
