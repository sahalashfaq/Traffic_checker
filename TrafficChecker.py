# main.py
import streamlit as st
import pandas as pd
import re
import time
import asyncio
import subprocess
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os

# ── Custom CSS Loader ────────────────────────────────────────────────────────
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

local_css("style.css")

# ── Check and install Chrome/Chromium dependencies ───────────────────────────
def check_chrome_installation():
    """Check if Chrome/Chromium is properly installed and install if needed"""
    try:
        # Try to install Chrome dependencies for Debian/Ubuntu
        st.info("Checking browser dependencies...")
        
        # Install Chrome via apt (for Debian-based systems like Streamlit Cloud)
        install_commands = [
            "apt-get update",
            "apt-get install -y wget gnupg",
            "wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -",
            'sh -c \'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list\'',
            "apt-get update",
            "apt-get install -y google-chrome-stable chromium-driver"
        ]
        
        for cmd in install_commands:
            try:
                subprocess.run(cmd, shell=True, check=True, capture_output=True)
            except:
                continue
        
        return True
    except Exception as e:
        st.warning(f"Dependency check: {str(e)[:100]}")
        return False

# ── Driver Factory (Fixed Version) ───────────────────────────────────────────
@st.cache_resource
def init_driver(headless_mode=True):
    chrome_options = Options()
    
    # Essential options for cloud deployment
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Window size
    chrome_options.add_argument("--window-size=1280,900")
    
    # Headless mode configuration
    if headless_mode:
        chrome_options.add_argument("--headless=new")
    else:
        st.warning("Running in VISIBLE mode – browser window will appear (only useful locally)")
        chrome_options.add_argument("--start-maximized")

    # Disable extensions for stability
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    
    # Memory optimization
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    
    # User agent to avoid detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Try multiple binary locations
    binary_locations = [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/local/bin/chrome",
        "/opt/google/chrome/chrome"
    ]
    
    for binary in binary_locations:
        if os.path.exists(binary):
            chrome_options.binary_location = binary
            st.success(f"Found Chrome at: {binary}")
            break
    else:
        st.warning("Chrome binary not found in standard locations. Trying default...")
    
    # Try multiple driver locations
    driver_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/usr/bin/chromium-driver",
        "/opt/chromedriver/chromedriver"
    ]
    
    driver_path = None
    for path in driver_paths:
        if os.path.exists(path):
            driver_path = path
            st.success(f"Found ChromeDriver at: {path}")
            break
    
    if not driver_path:
        # Try to install chromedriver automatically
        try:
            st.info("Attempting to install ChromeDriver...")
            subprocess.run("apt-get install -y chromium-chromedriver", shell=True, check=False)
            driver_path = "/usr/bin/chromedriver"
        except:
            st.error("ChromeDriver not found and could not be installed")
            st.stop()
    
    # Create service with error handling
    service = Service(
        executable_path=driver_path,
        service_args=['--verbose'],  # Enable verbose logging for debugging
        log_path='chromedriver.log'  # Log file for debugging
    )
    
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Execute CDP commands to avoid detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        st.success("✅ Chrome driver initialized successfully!")
        return driver
        
    except Exception as e:
        st.error("❌ Chromium driver initialization failed")
        st.error(f"Error details: {str(e)}")
        
        # Try fallback method with webdriver_manager
        try:
            st.info("Attempting fallback with webdriver_manager...")
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service as ChromeService
            
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            st.success("✅ Chrome driver initialized with webdriver_manager!")
            return driver
        except Exception as e2:
            st.error(f"Fallback also failed: {str(e2)}")
            st.error("""
            **Troubleshooting steps:**
            1. Make sure Chrome is installed: `apt-get install google-chrome-stable`
            2. Install ChromeDriver: `apt-get install chromium-chromedriver`
            3. Check permissions: `chmod +x /usr/bin/chromedriver`
            4. For Streamlit Cloud, add to requirements.txt:
               - selenium==4.15.0
               - webdriver-manager==4.0.1
            """)
            st.stop()

# ── Updated scraping function with better selectors ──────────────────────────
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
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)

        time.sleep(5)  # initial Cloudflare breathing room

        # Try to wait for clearance (best effort)
        start_cf = time.time()
        while time.time() - start_cf < max_wait:
            if any(c.get('name') == 'cf_clearance' for c in driver.get_cookies()):
                break
            time.sleep(1.5)

        # Wait for modal to appear
        WebDriverWait(driver, max_wait - 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
        )

        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")

        def safe_text(by, value):
            try:
                return modal.find_element(by, value).text.strip()
            except:
                return "N/A"

        # Updated selectors based on your provided XPath structure
        result["Website"] = safe_text(By.CSS_SELECTOR, "h2") or "N/A"

        # Traffic amount - main big number
        result["Organic Traffic"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[contains(@class,'css-vemh4e') or contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[2]/div/div/div/span")

        # Traffic value (usually $X.XX)
        result["Traffic Value"] = safe_text(
            By.XPATH,
            "//div[contains(@class,'ReactModalPortal')]//span[starts-with(text(),'$') or contains(@class,'css-6s0ffe')]"
        ) or safe_text(By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[2]/div[2]/div/div/div/span")

        # Top country
        country_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(1) tr:first-child")
        if country_row != "N/A":
            match = re.match(r"(.+?)\s+([\d.%]+)", country_row.strip())
            if match:
                result["Top Country"] = match.group(1).strip()
                result["Top Country Share"] = match.group(2)

        # Top keyword
        kw_row = safe_text(By.CSS_SELECTOR, "table:nth-of-type(2) tr:first-child")
        if kw_row != "N/A":
            match = re.match(r"(.+?)\s+(\d+)\s+([\d,K,M\.]+)", kw_row.strip())
            if match:
                result["Top Keyword"] = match.group(1)
                result["Keyword Position"] = match.group(2)
                result["Top Keyword Traffic"] = match.group(3)

        result["Status"] = "Success"

    except Exception as e:
        result["Organic Traffic"] = f"Error: {str(e)[:70]}..."
        result["Status"] = "Failed"

    return result

# ── Batch processing ─────────────────────────────────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    driver = init_driver(headless_mode=headless)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=2)  # 2 is safer in visible mode

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

# Initialize Chrome on first load
if 'chrome_initialized' not in st.session_state:
    with st.spinner("Initializing Chrome driver..."):
        check_chrome_installation()
        st.session_state.chrome_initialized = True

# Controls
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"])
with col2:
    max_wait = st.number_input("Max wait per URL (sec)", 30, 180, 70, 5)
with col3:
    headless = st.checkbox("Run in Headless mode", value=True,
                          help="Uncheck to see browser actions (only useful when running locally)")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
        url_col = st.selectbox("Select URL/Domain column", df.columns)
        urls = df[url_col].dropna().unique().tolist()

        st.markdown(f"**{len(urls)} unique URLs/domains found**")

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

