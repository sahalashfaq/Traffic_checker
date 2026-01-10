import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

st.set_page_config(page_title="Bulk Traffic Checker (Cloud Compatible)", layout="centered")

st.markdown("""
# Bulk Traffic Checker – Ahrefs (Streamlit Cloud Version)
Get website traffic information from Ahrefs in batch.

**Important 2026 reality check:**
- Cloudflare protection is very strong → **many domains will fail**
- Success rate usually 5–25% depending on luck & current Cloudflare rules
- For serious use → consider residential proxies or official Ahrefs API
""")

# Settings
col1, col2 = st.columns([3, 2])
with col1:
    timeout = st.slider("Max wait time per domain (seconds)", 30, 180, 60, 5)
with col2:
    max_retries = st.number_input("Retries per domain", 1, 5, 2)

uploaded_file = st.file_uploader("Upload CSV or XLSX with domains/URLs", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        st.dataframe(df.head(8))
        
        domain_col = st.selectbox("Column containing domains/URLs", df.columns)
        
        if st.button("Start Processing", type="primary"):
            
            # ── Driver Setup (same as working Facebook scraper) ─────────────────────
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.binary_location = "/usr/bin/chromium-browser"  # ← important!

            service = Service("/usr/bin/chromedriver")
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            results = []
            progress = st.progress(0)
            status_text = st.empty()
            result_table = st.empty()
            
            domains = df[domain_col].dropna().unique().tolist()
            total = len(domains)
            
            for idx, domain in enumerate(domains, 1):
                status_text.markdown(f"Processing {idx}/{total}: **{domain}**")
                
                row = {"Domain": domain, "Status": "Failed"}
                
                for attempt in range(max_retries):
                    try:
                        url = f"https://ahrefs.com/traffic-checker/?input={domain}&mode=domain"
                        driver.get(url)
                        time.sleep(5)  # First Cloudflare chance
                        
                        # Wait up to (timeout-10) seconds for modal or clearance
                        WebDriverWait(driver, timeout-10).until(
                            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".ReactModalPortal")) > 0
                        )
                        
                        modal = driver.find_element(By.CSS_SELECTOR, ".ReactModalPortal")
                        
                        def safe_text(css):
                            try: return modal.find_element(By.CSS_SELECTOR, css).text.strip()
                            except: return "—"
                        
                        website = safe_text("h2")
                        traffic = safe_text("span[class*='css-vemh4e']")  # main traffic number
                        value = safe_text("span[class*='css-6s0ffe']")     # $ value
                        
                        # Top country (first row)
                        country_row = safe_text("table:nth-of-type(1) tr:first-child")
                        country, share = "—", "—"
                        if country_row != "—":
                            parts = re.split(r'\s+', country_row.strip(), maxsplit=1)
                            if len(parts) >= 2:
                                country = parts[0]
                                share = parts[1]
                        
                        row.update({
                            "Website": website,
                            "Organic Traffic": traffic,
                            "Traffic Value": value,
                            "Top Country": country,
                            "Top Country Share": share,
                            "Status": "Success"
                        })
                        break  # success → no more retries
                        
                    except Exception as e:
                        if attempt == max_retries - 1:
                            row["Status"] = f"Failed after {max_retries} tries"
                
                results.append(row)
                progress.progress(idx / total)
                result_table.dataframe(pd.DataFrame(results))
            
            driver.quit()
            
            st.success("Processing finished!")
            
            if results:
                final_df = pd.DataFrame(results)
                csv = final_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Results CSV",
                    data=csv,
                    file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
                
    except Exception as e:
        st.error(f"Error reading file: {e}")

st.markdown("---")
st.caption("Most realistic approach for Streamlit Community Cloud in 2026. For much better success rate use VPS + residential proxies + SeleniumBase UC mode.")
