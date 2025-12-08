import streamlit as st
import pandas as pd
from seleniumbase import Driver
from selenium.webdriver.common.by import By
import time
st.markdown('''<style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,100;1,200;1,300;1,400;1,500;1,600;1,700;1,800;1,900&display=swap');

            * {
                font-family: "Poppins", sans-serif;
                font-weight: 600;
                color: var(--black);
                box-sizing: border-box;
            }
            
            :root {
                --primary-color: #000000;
                --secondary-color: #FD653D;
                --background: #f5f5f5;
                --background-color-light: #e7e7ff5e;
                --white: white;
                --border-color: #E6EDFF;
                --indigo-color: #FD653D;
                --red-color: #FF3B30;
                --green-color: #146356;
                --orange-color: #FF9500;
                --grey-color: #7C8DB5;
                --border-grey-color: #7c8db547;
                --font-family-1: "Exo", sans-serif;
                --font-family-2: "Albert Sans", sans-serif;
                --font-family-3: "Poppins", sans-serif;
                --black: #09112c;
                --aside-background-white: rgba(255, 255, 255, 0.457);
                --normal_shaodow: 0px 0px 2px grey !important;
            }
            
            body {
                color: var(--black);
                line-height: 1.6;
                max-width: 1500px !important;
                margin: 0 auto;
            }
            
            div[data-test-connection-state="CONNECTED"] {
                background: var(--background);
            }
            
            header,
            footer {
                display: none !important;
            }
            
            div[data-testid="stFileUploader"] {
                width: 100%;
            }
            
            div[data-testid="stFileUploader"] * {
                padding: 0px;
            }
            
            div[data-testid="stFileUploader"] .st-emotion-cache-fis6aj {
                padding-top: 10px;
                border-top: 2px solid var(--border-grey-color);
                border-top-style: dashed;
                margin-top: 20px;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) {
                background: var(--white) !important;
                box-shadow: var(--normal_shaodow);
                padding: 10px 10px !important;
                padding-right: 15px !important;
                border-radius: 10px !important;
                cursor: pointer;
                margin: 10px 0;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) button {
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                background: var(--black) !important;
                border-radius: 10px;
                white-space: nowrap;
                padding: 15px 30px;
                color: var(--white) !important;
                letter-spacing: 1px;
                font-size: small;
                font-weight: 600;
                border: none;
                position: relative;
                text-transform: capitalize;
                outline: none;
                margin-right: -5px;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) button:hover {
                background: var(--indigo-color) !important;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) span:has(svg) {
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 10px;
                border-radius: 10px;
                background: var(--indigo-color);
                margin-left: -5px;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) span:has(svg) svg {
                fill: var(--white);
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) small {
                font-weight: 500;
            }
            
            section[data-testid="stFileUploaderDropzone"]:has(input[data-testid="stFileUploaderDropzoneInput"]) * {
                text-transform: capitalize;
            }
            
            p {
                font-weight: 550;
            }
            
            div[data-testid="stFileUploaderFile"] {
                background: var(--white);
                box-shadow: var(--normal_shaodow);
                padding: 10px;
                width: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                gap: 10px;
                border-radius: 10px;
            }
            
            div[data-testid="stFileUploaderFile"] div.stFileUploaderFileData {
                width: 100% !important;
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                height: 100%;
                margin-top: 5px;
            }
            
            div[data-testid="stFileUploaderFile"] div.stFileUploaderFileData small {
                margin-top: -5px;
                padding-left: 10px;
                border-left: 2px solid var(--border-grey-color);
                border-left-style: dashed !important;
                height: 100%;
            }
            
            div[data-testid="stFileUploaderDeleteBtn"] button {
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 10px;
                position: relative;
                right: 5px;
                background: var(--background) !important;
                border-radius: 10px;
                font-weight: 600;
                box-shadow: inset var(--normal_shaodow);
                color: var(--black) !important;
            }
            
            div.stFileUploaderFileName {
                font-weight: 500;
                color: var(--black);
            }
            
            div[data-testid="stFileUploaderFile"] .st-emotion-cache-10ix4kq:has(svg) {
                background: var(--black);
                border-radius: 10px;
                padding: 10px;
            }
            
            div[data-testid="stFileUploaderFile"] .st-emotion-cache-10ix4kq:has(svg) svg {
                fill: var(--white);
            }
            
            button[kind="secondary"] {
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                background: var(--black) !important;
                border-radius: 10px;
                white-space: nowrap;
                padding: 15px 30px;
                color: var(--white) !important;
                border: none;
                position: relative;
                outline: none;
            }
            
            button[kind="secondary"] p {
                display: flex;
                justify-content: center;
                align-items: center;
                text-align: center;
                text-transform: capitalize;
                letter-spacing: 1px;
                font-size: small;
                font-weight: 600;
                color: var(--white);
            }
            
            button[kind="secondary"]:hover {
                background: var(--indigo-color) !important;
            }
            
            div.stSelectbox {
                background: var(--white);
                padding: 15px;
                box-shadow: var(--normal_shaodow);
                border-radius: 7px;
                display: flex;
                justify-content: flex-start;
                align-items: flex-start;
                text-align: left;
                gap: 5px;
                flex-direction: column;
            }
            
            div[data-baseweb="select"] .st-au {
                background: var(--background) !important;
                box-shadow: var(--normal_shaodow);
                color: var(--black) !important;
                border-radius: 5px;
                cursor: pointer;
            }
            
            div[data-baseweb="select"] * {
                font-weight: 500 !important;
                border: none !important;
                display: flex;
                justify-content: flex-start;
                align-items: center;
                text-align: left;
            }
            
            li[role="option"] * {
                font-weight: 500 !important;
            }
            
            .div[role="progressbar"] .st-dl {
                background: var(--indigo-color);
            }
            
            .h1 {
                font-size: xx-large;
            }
            
            strong {
                font-weight: 500 !important;
            }
            
            code {
                background: var(--white) !important;
                box-shadow: var(--normal_shaodow);
                padding: 10px;
                margin-right: 10px;
            }
            
            div[data-testid="stNumberInputContainer"] {
                border: 3px solid rgba(128, 128, 128, 0.082) !important;
                outline: none;
                border-radius: 10px;
            }
            
            div[data-testid="stNumberInputContainer"] input {
                background: var(--white);
            }
            
            button[data-testid="stNumberInputStepUp"] {
                background: var(--black) !important;
            
            }
            
            button[data-testid="stNumberInputStepDown"] {
                background: var(--indigo-color) !important;
            
            }
            
            button[data-testid="stNumberInputStepUp"] *,
            button[data-testid="stNumberInputStepDown"] * {
                color: var(--white);
            }
            
            p a {
                color: var(--indigo-color) !important;
            }
            
            p a * {
                color: var(--indigo-color) !important;
            }
            
            p.states_p {
                margin: 0px !important;
                justify-content: space-between;
                display: flex;
                align-items: center;
                text-align: center;
                padding: 0 !important;
            }
            
            div:has(> p.states_p) {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            
            p.states_p b {
                color: var(--indigo-color);
            }
            
            div:has(input) {
                outline: rgb(0, 0, 0) none;
                outline: none;
            }
            
            div.stTextInput {
                display: flex;
                justify-content: flex-start;
                align-items: flex-start;
                text-align: left;
                gap: 5px;
                flex-direction: column;
                border-radius: 10px;
            }
            
            div.stTextInput div:has(input) {
                border: 2px solid rgba(128, 128, 128, 0.082) !important;
            }
            
            div.stTextInput input {
                background: var(--white);
                border-radius: 7px;
                box-shadow: var(--normal_shaodow);
                font-size: small;
            }
            
            div[data-baseweb="input"] {
                border: none !important;
            }
            
            .h1 {
                font-size: xx-large !important;
                font-weight: 600;
                position: relative;
                line-height: 80%;
                width: max-content;
            }
            p.h1::before{
                content: '';
                height: 10px;
                width: 10px;
                border-radius: 50px;
                display: flex;
                position: absolute;
                right: -15px;
                bottom: 1px;
                background: var(--indigo-color);
            }
            
            div[direction="row"] {
                display: flex;
                flex-direction: column;
                width: 100%;
            }
            
            div[direction="row"] div:has(div div) {
                width: 100%;
            }
            
            div div div div div div div div div div div:has(p.h1) {
                display: flex;
                flex-direction: column;
                gap: 0px;
                margin-bottom: 30px;
                padding-bottom: 10px;
                border-bottom: 2px solid #8080803b;
                border-bottom-style: dashed;
            }
            
            div div div div div div div div div:has(p+p) p:nth-of-type(2) {
                margin-top: -5px;
                font-weight: 400;
                color: grey;
            }
            .p strong{
                color: var(--indigo-color);
                margin-left: 10px;
                text-decoration: underline;
            }
            </style>''', unsafe_allow_html=True)
st.set_page_config(page_title="Bulk Traffic Checker", layout="centered")
st.markdown("<p class='h1'>Bulk Traffic Checker</p><p>Get the Website Traffic Information in Bulk From Ahref.</p>", unsafe_allow_html=True)

# --- Settings ---
col1, col2 = st.columns(2)
with col1:
    timeout = st.number_input("Safety timeout per domain (seconds)", 40, 180, 70, 10)
with col2:
    mode = st.selectbox("Mode", ["Headless (Fastest)", "Visible (debug)"], index=0)

headless = (mode == "Headless (Fastest)")

uploaded_file = st.file_uploader("Upload CSV/XLSX with domains", type=["csv", "xlsx"])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
    st.dataframe(df.head(10), use_container_width=True)

    domain_col = st.selectbox("Column with Websites URLs", df.columns)

    if st.button("Start Extraction", type="secondary"):

        results = []
        progress = st.progress(0)
        status = st.empty()
        table = st.empty()

        driver = Driver(uc=True, headless=headless, incognito=True, disable_gpu=True)

        try:
            for idx, domain in enumerate(df[domain_col].dropna(), 1):
                row = {"Domain": domain}
                status.markdown(f"<p class='p'>({idx} / {len(df)}): <strong>{domain}</strong></p>",unsafe_allow_html=True)

                success = False
                for attempt in range(3):  # Retry up to 3 times per domain
                    try:
                        # Open Ahrefs with reconnect
                        driver.uc_open_with_reconnect(
                            f"https://ahrefs.com/traffic-checker/?input={domain}&mode=domain",
                            reconnect_time=5
                        )

                        # Click "Check traffic" if present
                        try:
                            btn = driver.find_element(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'check traffic')]")
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1.5)
                        except:
                            pass

                        # Enhanced Cloudflare handling
                        if not any(c["name"] == "cf_clearance" for c in driver.get_cookies()):
                            cf_start = time.time()
                            while time.time() - cf_start < 40:  # Longer timeout
                                try:
                                    # Explicitly check for CAPTCHA iframe
                                    captcha_iframe = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare.com']")
                                    if captcha_iframe:
                                        driver.switch_to.frame(captcha_iframe[0])
                                        checkbox = driver.find_element(By.ID, "cf-chl-widget-0")  # Common CAPTCHA checkbox ID
                                        driver.execute_script("arguments[0].click();", checkbox)
                                        driver.switch_to.default_content()
                                    else:
                                        driver.uc_gui_click_captcha()  # Fallback to built-in
                                except:
                                    pass
                                
                                if any(c["name"] == "cf_clearance" for c in driver.get_cookies()):
                                    break
                                time.sleep(0.8)  # Tighter loop for faster detection

                            if not any(c["name"] == "cf_clearance" for c in driver.get_cookies()):
                                if headless:
                                    st.warning(f"CAPTCHA unsolved in headless mode for {domain}. Try visible mode.")
                                    break
                                else:
                                    st.info(f"Manual CAPTCHA may be needed for {domain}. Solve it in the browser window.")
                                    time.sleep(10)  # Give time for manual solve

                        # Wait for modal title (data indicator)
                        driver.wait_for_element_visible("//div[contains(@class,'ReactModalPortal')]//h2", timeout=20)

                        # Extract data
                        website = driver.find_element(By.XPATH, "//div[contains(@class,'ReactModalPortal')]//h2").text.strip()

                        traffic = driver.find_element(By.XPATH, 
                            "//div[contains(@class,'ReactModalPortal')]//span[contains(text(),'K') or contains(text(),'M') or contains(text(),'B')]"
                        ).text.strip()

                        value = driver.find_element(By.XPATH, 
                            "//div[contains(@class,'ReactModalPortal')]//span[starts-with(text(),'$')]"
                        ).text.strip()

                        top_country = driver.find_element(By.XPATH, "(//div[contains(@class,'ReactModalPortal')]//table)[1]//tr[1]//td[1]").text.strip()
                        top_keyword = driver.find_element(By.XPATH, "(//div[contains(@class,'ReactModalPortal')]//table)[2]//tr[1]//td[1]").text.strip()

                        row.update({
                            "Organic Traffic": traffic,
                            "Traffic Value": value,
                            "Top Country": top_country,
                            "Top Keyword": top_keyword,
                            "Status": "Success"
                        })
                        success = True
                        break  # Exit retry loop on success

                    except Exception as e:
                        if attempt == 2:  # Final failure after retries
                            row.update({
                                "Organic Traffic": "—",
                                "Traffic Value": "—",
                                "Top Country": "—",
                                "Top Keyword": "—",
                                "Status": f"Failed Due to CLoudFlare!"
                            })

                results.append(row)
                progress.progress(idx / len(df))
                table.dataframe(pd.DataFrame(results), use_container_width=True)

        finally:
            driver.quit()

        st.balloons()

        # Download
        csv = pd.DataFrame(results).to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Results CSV",
            data=csv,
            file_name=f"ahrefs_traffic_{time.strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )