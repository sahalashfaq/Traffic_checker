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
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
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
def create_driver(headless_mode=True):
    """Create a new driver instance - NOT cached to allow recreation"""
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
    
    if headless_mode:
        options.add_argument("--headless=new")
    
    try:
        driver = uc.Chrome(
            version_main=144,
            options=options,
            use_subprocess=True,
            driver_executable_path=None
        )
        
        # Set timeouts
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(5)
        
        if not headless_mode:
            driver.maximize_window()
        
        return driver
    
    except Exception as e:
        try:
            driver = uc.Chrome(options=options, use_subprocess=True)
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(5)
            if not headless_mode:
                driver.maximize_window()
            return driver
        except Exception as e2:
            raise Exception(f"Failed to create driver: {str(e2)}")

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
        time.sleep(4)
        
        # Check for Cloudflare challenge
        page_source = driver.page_source.lower()
        if "cloudflare" in page_source or "just a moment" in page_source or "checking your browser" in page_source:
            result["Debug"] = "CF detected - waiting..."
            
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
                        result["Debug"] = "CF cleared"
                        break
                    
                    # Check if page content changed
                    current_source = driver.page_source.lower()
                    if "cloudflare" not in current_source and "just a moment" not in current_source:
                        cleared = True
                        result["Debug"] = "CF cleared (content)"
                        break
                        
                except:
                    pass
                
                time.sleep(2)
            
            if not cleared:
                result["Debug"] = "CF blocked"
                result["Status"] = "Blocked by Cloudflare"
                return result
        
        # Wait for the modal to appear
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal OK"
        except TimeoutException:
            # Try alternative selectors
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Modal']"))
                )
                result["Debug"] += " | Modal OK (alt)"
            except:
                result["Debug"] += " | Modal FAIL"
                result["Status"] = "Modal not found"
                return result
        
        # Give extra time for data to populate
        time.sleep(4)
        
        # Helper function to extract text using multiple methods
        def get_text_multi(xpaths_and_css):
            """Try multiple selectors and extraction methods"""
            for selector_type, selector_value in xpaths_and_css:
                try:
                    if selector_type == "xpath":
                        elem = driver.find_element(By.XPATH, selector_value)
                    else:  # css
                        elem = driver.find_element(By.CSS_SELECTOR, selector_value)
                    
                    # Try multiple text extraction methods
                    text = elem.text.strip()
                    if text:
                        return text
                    
                    # Try innerText
                    text = elem.get_attribute("innerText")
                    if text and text.strip():
                        return text.strip()
                    
                    # Try textContent
                    text = elem.get_attribute("textContent")
                    if text and text.strip():
                        return text.strip()
                    
                except Exception as e:
                    continue
            return "N/A"
        
        # Extract Website Name - multiple selectors
        website_selectors = [
            ("xpath", "/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p"),
            ("css", ".ReactModalPortal h2"),
            ("xpath", "//div[contains(@class,'ReactModalPortal')]//h2"),
            ("xpath", "//div[contains(@class,'ReactModalPortal')]//p[1]"),
            ("css", ".ReactModalPortal p:first-of-type"),
            ("xpath", "//h2[contains(@class,'')]"),
        ]
        result["Website Name"] = get_text_multi(website_selectors)
        
        # Extract Organic Traffic - multiple selectors
        traffic_selectors = [
            ("xpath", "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span"),
            ("xpath", "//div[contains(@class,'ReactModalPortal')]//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"),
            ("css", "span[class*='css-vemh4e']"),
            ("xpath", "//div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span"),
            ("xpath", "//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')][1]"),
            ("xpath", "//div[contains(@class,'traffic')]//span"),
        ]
        result["Organic Traffic"] = get_text_multi(traffic_selectors)
        
        # Extract Traffic Worth - multiple selectors
        worth_selectors = [
            ("xpath", "/html/body/div[6]/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span"),
            ("xpath", "//span[starts-with(text(),'$')]"),
            ("css", "span[class*='css-6s0ffe']"),
            ("xpath", "//span[contains(text(),'$')][1]"),
            ("xpath", "//div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span"),
        ]
        result["Traffic Worth"] = get_text_multi(worth_selectors)
        
        # Check if we got meaningful data
        if result["Organic Traffic"] != "N/A" or result["Website Name"] != "N/A":
            result["Status"] = "Success"
            result["Debug"] += " | Data OK"
        else:
            result["Status"] = "No data found"
            result["Debug"] += " | Data FAIL"
    
    except WebDriverException as e:
        result["Status"] = "Driver Error"
        result["Debug"] = f"Driver crash: {str(e)[:80]}"
    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Error: {str(e)[:80]}"
    
    return result

# ── Batch processing with driver restart logic ──────────────────────────────
async def process_urls(urls, max_wait, headless, progress_callback=None):
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    
    results = []
    total = len(urls)
    start = time.time()
    
    # Create initial driver
    driver = None
    driver_created = False
    
    for i, url in enumerate(urls):
        # Create or recreate driver if needed
        if driver is None or not driver_created:
            try:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                
                driver = create_driver(headless_mode=headless)
                driver_created = True
            except Exception as e:
                result = {
                    "URL": url,
                    "Website Name": "N/A",
                    "Organic Traffic": "N/A",
                    "Traffic Worth": "N/A",
                    "Status": "Driver Init Failed",
                    "Debug": str(e)[:100]
                }
                results.append(result)
                continue
        
        # Try to scrape
        try:
            row = await loop.run_in_executor(executor, scrape_ahrefs_traffic, driver, url, max_wait)
            results.append(row)
            
            # If driver error, mark for recreation
            if "Driver" in row["Status"] or "Connection" in row["Debug"]:
                driver_created = False
                
        except Exception as e:
            result = {
                "URL": url,
                "Website Name": "N/A",
                "Organic Traffic": "N/A",
                "Traffic Worth": "N/A",
                "Status": "Exception",
                "Debug": str(e)[:100]
            }
            results.append(result)
            # Mark driver for recreation
            driver_created = False

        elapsed = time.time() - start
        eta = (elapsed / (i+1)) * (total - i - 1) if i < total-1 else 0
        success = sum(1 for r in results if r["Status"] == "Success")

        if progress_callback:
            progress_callback(i+1, total, success, round(eta/60, 1), results)
        
        # Small delay between requests
        time.sleep(2)

    # Cleanup
    if driver:
        try:
            driver.quit()
        except:
            pass
    
    return results

# ── Streamlit UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ahrefs Traffic Bulk Checker", layout="centered")

st.title("🔍 Ahrefs Traffic Checker – Bulk Extraction")
st.caption("2026 Cloud Version • Auto Driver Restart • Multi-Selector Fallback")

# Show initialization message
with st.expander("ℹ️ System Info", expanded=False):
    st.write("- **Driver**: Auto-restart on failure")
    st.write("- **Selectors**: Multiple XPath + CSS fallbacks")
    st.write("- **Cloudflare**: 30s clearance timeout")
    st.write("- **Mode**: Headless on cloud, visible locally")

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
                
                # Show results table
                df_results = pd.DataFrame(current_results)
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
### ℹ️ Debug Guide
- **"Driver crash"**: ChromeDriver died, will auto-restart
- **"CF blocked"**: Cloudflare challenge failed
- **"Data FAIL"**: Modal loaded but selectors didn't find data
- **"Modal FAIL"**: Page didn't render the popup
""")
