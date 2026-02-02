# main.py
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

# ── Scraping function ────────────────────────────────────────────────────────
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
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        
        # Navigate to URL
        driver.get(full_url)
        time.sleep(3)
        
        # Check for Cloudflare challenge
        page_source = driver.page_source.lower()
        if "cloudflare" in page_source or "just a moment" in page_source or "checking your browser" in page_source:
            result["Debug"] = "Cloudflare challenge detected - waiting for clearance..."
            
            # Wait longer for Cloudflare
            max_cf_wait = min(max_wait, 30)
            start_cf = time.time()
            cleared = False
            
            while time.time() - start_cf < max_cf_wait:
                try:
                    # Check if cf_clearance cookie exists
                    cookies = driver.get_cookies()
                    if any(c.get('name') == 'cf_clearance' for c in cookies):
                        cleared = True
                        result["Debug"] = "Cloudflare cleared successfully"
                        break
                    
                    # Check if page content changed
                    current_source = driver.page_source.lower()
                    if "cloudflare" not in current_source and "just a moment" not in current_source:
                        cleared = True
                        result["Debug"] = "Page loaded after Cloudflare"
                        break
                        
                except:
                    pass
                
                time.sleep(2)
            
            if not cleared:
                result["Debug"] = "Cloudflare challenge NOT cleared - blocked"
                result["Status"] = "Blocked by Cloudflare"
                return result
        
        # Wait for the modal to appear
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal found"
        except TimeoutException:
            # Try alternative selectors
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Modal']"))
                )
                result["Debug"] += " | Alternative modal found"
            except:
                result["Debug"] += " | Modal NOT found - page may not have loaded"
                result["Status"] = "Modal not found"
                return result
        
        # Give extra time for data to populate
        time.sleep(3)
        
        # Helper function to safely extract text from exact XPath
        def safe_text_xpath(xpath):
            try:
                element = driver.find_element(By.XPATH, xpath)
                text = element.text.strip()
                return text if text else "N/A"
            except:
                return "N/A"
        
        # Extract Website Name using exact XPath
        website_xpath = "/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p"
        result["Website Name"] = safe_text_xpath(website_xpath)
        
        # If exact path fails, try fallback selectors
        if result["Website Name"] == "N/A":
            website_selectors = [
                (By.CSS_SELECTOR, ".ReactModalPortal h2"),
                (By.XPATH, "//div[contains(@class,'ReactModalPortal')]//h2"),
                (By.XPATH, "//div[contains(@class,'ReactModalPortal')]//p[1]"),
                (By.CSS_SELECTOR, ".ReactModalPortal p:first-of-type"),
            ]
            for selector_type, selector_value in website_selectors:
                try:
                    elem = driver.find_element(selector_type, selector_value)
                    text = elem.text.strip()
                    if text:
                        result["Website Name"] = text
                        break
                except:
                    continue
        
        # Extract Organic Traffic using exact XPath
        traffic_xpath = "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span"
        result["Organic Traffic"] = safe_text_xpath(traffic_xpath)
        
        # If exact path fails, try fallback selectors
        if result["Organic Traffic"] == "N/A":
            traffic_selectors = [
                (By.XPATH, "//div[contains(@class,'ReactModalPortal')]//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"),
                (By.CSS_SELECTOR, "span[class*='css-vemh4e']"),
                (By.XPATH, "//span[contains(@class,'traffic') or contains(@class,'visits')]"),
                (By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[2]/div/div/div/span"),
            ]
            for selector_type, selector_value in traffic_selectors:
                try:
                    elem = driver.find_element(selector_type, selector_value)
                    text = elem.text.strip()
                    if text and any(char in text for char in ['K', 'M', 'B', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
                        result["Organic Traffic"] = text
                        break
                except:
                    continue
        
        # Extract Traffic Worth using exact XPath
        worth_xpath = "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span"
        result["Traffic Worth"] = safe_text_xpath(worth_xpath)
        
        # If exact path fails, try fallback selectors
        if result["Traffic Worth"] == "N/A":
            worth_selectors = [
                (By.XPATH, "//span[starts-with(text(),'$')]"),
                (By.CSS_SELECTOR, "span[class*='css-6s0ffe']"),
                (By.XPATH, "//span[contains(text(),'$')]"),
                (By.XPATH, "//div[1]/div[1]/div[2]/div[1]/div[1]/div[2]/div[2]/div/div/div/span"),
            ]
            for selector_type, selector_value in worth_selectors:
                try:
                    elem = driver.find_element(selector_type, selector_value)
                    text = elem.text.strip()
                    if text and '$' in text:
                        result["Traffic Worth"] = text
                        break
                except:
                    continue
        
        # Check if we got meaningful data
        if result["Organic Traffic"] != "N/A" or result["Website Name"] != "N/A":
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data found"
            result["Debug"] += " | Elements found but no data extracted"
    
    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:150]}"
        result["Organic Traffic"] = f"Error: {str(e)[:50]}"
    
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
- **All "N/A" results**: Cloudflare is blocking requests. Try:
  - Increase wait time to 90+ seconds
  - Run during off-peak hours
  - Consider using residential proxies (not included in this version)
- **"Modal not found"**: Page didn't load properly, increase timeout
- **"Blocked by Cloudflare"**: Strong anti-bot protection detected
- Check the **Debug** column for specific error details

### 📍 XPath Selectors Used:
- **Website Name**: `/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p`
- **Organic Traffic**: `/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span`
- **Traffic Worth**: `/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span`
""")
