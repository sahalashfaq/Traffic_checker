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
        time.sleep(5)
        
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
                        result["Debug"] = "CF cleared"
                        break
                        
                except:
                    pass
                
                time.sleep(2)
            
            if not cleared:
                result["Debug"] = "CF blocked"
                result["Status"] = "Blocked by Cloudflare"
                return result
        
        # Wait for the ReactModalPortal specifically
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ReactModalPortal"))
            )
            result["Debug"] += " | Modal found"
        except TimeoutException:
            result["Debug"] += " | Modal NOT found"
            result["Status"] = "Modal not found"
            return result
        
        # Give extra time for data to populate inside modal
        time.sleep(5)
        
        # STRICT: Only use the exact selectors provided
        # Helper function to extract text with validation
        def safe_extract(selector_type, selector_value, field_name):
            """Extract text and validate it's actually from the modal data"""
            try:
                if selector_type == "xpath":
                    elem = driver.find_element(By.XPATH, selector_value)
                else:  # css
                    elem = driver.find_element(By.CSS_SELECTOR, selector_value)
                
                # Try multiple text extraction methods
                text = elem.text.strip()
                if not text:
                    text = elem.get_attribute("innerText")
                    if text:
                        text = text.strip()
                if not text:
                    text = elem.get_attribute("textContent")
                    if text:
                        text = text.strip()
                
                # Validate the text is NOT Ahrefs UI elements
                if text and text not in ["", "N/A"]:
                    # Reject common Ahrefs UI text
                    reject_list = [
                        "Check any website",
                        "Keywords Explorer",
                        "Site Explorer",
                        "Content Explorer",
                        "Rank Tracker",
                        "Site Audit",
                        "Ahrefs",
                        "SEO Tools",
                        "Backlinks",
                        "organic",
                        "traffic",
                        "worth"
                    ]
                    
                    text_lower = text.lower()
                    for reject in reject_list:
                        if reject.lower() in text_lower and len(text) < 50:
                            # This is likely UI text, not data
                            return "N/A"
                    
                    return text
                
                return "N/A"
                
            except Exception as e:
                return "N/A"
        
        # EXACT SELECTOR 1: Website Name
        # XPath: /html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p
        website_xpath = "/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p"
        website_name = safe_extract("xpath", website_xpath, "Website Name")
        
        # Validate it looks like a domain/website name
        if website_name != "N/A":
            # Should contain domain-like text
            if "." in website_name or "www" in website_name.lower() or len(website_name) > 4:
                result["Website Name"] = website_name
                result["Debug"] += " | Name OK"
            else:
                result["Debug"] += " | Name invalid"
        else:
            result["Debug"] += " | Name N/A"
        
        # EXACT SELECTOR 2: Organic Traffic
        # CSS: .ReactModalPortal/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[1]/div[2]/div/div/div/span
        # Convert to proper CSS selector
        traffic_css = ".ReactModalPortal > div > div > div > div > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div > div > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div > div > div > span"
        traffic_value = safe_extract("css", traffic_css, "Organic Traffic")
        
        # Validate it looks like traffic numbers (contains K, M, B, or numbers)
        if traffic_value != "N/A":
            if any(char in traffic_value for char in ['K', 'M', 'B', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
                # Should NOT contain dollar sign (that's worth, not traffic)
                if '$' not in traffic_value:
                    result["Organic Traffic"] = traffic_value
                    result["Debug"] += " | Traffic OK"
                else:
                    result["Debug"] += " | Traffic has $"
            else:
                result["Debug"] += " | Traffic invalid"
        else:
            result["Debug"] += " | Traffic N/A"
        
        # EXACT SELECTOR 3: Traffic Worth
        # CSS: .ReactModalPortal/div/div/div/div/div[2]/div[1]/div[1]/div/div/div[1]/div[2]/div[2]/div/div/div/span
        worth_css = ".ReactModalPortal > div > div > div > div > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div > div > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div > div > div > span"
        worth_value = safe_extract("css", worth_css, "Traffic Worth")
        
        # Validate it looks like money (contains $)
        if worth_value != "N/A":
            if '$' in worth_value:
                result["Traffic Worth"] = worth_value
                result["Debug"] += " | Worth OK"
            else:
                result["Debug"] += " | Worth no $"
        else:
            result["Debug"] += " | Worth N/A"
        
        # Final status
        if result["Organic Traffic"] != "N/A" or result["Website Name"] != "N/A" or result["Traffic Worth"] != "N/A":
            result["Status"] = "Success"
        else:
            result["Status"] = "No valid data"
            result["Debug"] += " | All fields empty/invalid"
    
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
        time.sleep(3)

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
st.caption("2026 Cloud Version • Strict Validation • Exact Selectors Only")

# Show initialization message
with st.expander("ℹ️ System Info", expanded=False):
    st.write("- **Selectors**: Using EXACT paths provided")
    st.write("- **Validation**: Rejects Ahrefs UI text, only accepts data")
    st.write("- **Wait time**: 5s after modal for data to populate")
    st.write("- **Driver**: Auto-restart on failure")

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
- **"Name invalid"**: Found text but doesn't look like a domain
- **"Traffic has $"**: Traffic selector grabbed worth instead
- **"Worth no $"**: Worth selector grabbed traffic instead
- **"All fields empty/invalid"**: Modal loaded but data validation failed

### 📍 Exact Selectors Being Used:
1. **Website Name**: `/html/body/div[6]/div/div/div/div/div[1]/div/div[1]/p`
2. **Organic Traffic**: `.ReactModalPortal > div > ... > span` (converted from your CSS path)
3. **Traffic Worth**: `.ReactModalPortal > div > ... > span` (converted from your CSS path)
""")
