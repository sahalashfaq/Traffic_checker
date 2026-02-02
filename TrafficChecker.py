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
        # Use correct parameter name (input → not always needed, but safer)
        full_url = f"https://ahrefs.com/traffic-checker/?input={url}&mode=subdomains"
        driver.get(full_url)
        time.sleep(2.5)

        # ── Cloudflare handling ───────────────────────────────────────
        page_source_lower = driver.page_source.lower()
        if any(x in page_source_lower for x in ["cloudflare", "just a moment", "checking your browser", "cf-browser-verification"]):
            result["Debug"] = "Cloudflare detected → waiting longer..."
            max_cf = min(max_wait, 45)
            start = time.time()
            cleared = False

            while time.time() - start < max_cf:
                cookies = driver.get_cookies()
                if any(c.get('name') == 'cf_clearance' for c in cookies):
                    cleared = True
                    result["Debug"] = "Cloudflare cleared (cf_clearance cookie found)"
                    break
                current = driver.page_source.lower()
                if all(x not in current for x in ["cloudflare", "just a moment", "checking your browser"]):
                    cleared = True
                    result["Debug"] = "Cloudflare screen disappeared"
                    break
                time.sleep(1.8)

            if not cleared:
                result["Debug"] += " | Cloudflare NOT cleared"
                result["Status"] = "Blocked by Cloudflare"
                return result

        # ── Wait for results area ─────────────────────────────────────
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Modal'], [class*='modal'], .ReactModalPortal"))
            )
            result["Debug"] += " | Modal / portal found"
        except TimeoutException:
            result["Debug"] += " | No modal detected after wait"
            # Some versions no longer use classic modal — try to find result cards anyway
            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='traffic'], [class*='visits'], [class*='value']"))
                )
                result["Debug"] += " | Found traffic-related elements anyway"
            except:
                result["Status"] = "No result container found"
                return result

        time.sleep(2.5)  # let React/Vue/etc. finish rendering

        # ── Try to get website/domain name ────────────────────────────────
        candidates = driver.find_elements(By.CSS_SELECTOR,
            "h1, h2, h3, .ReactModalPortal p, [class*='domain'], [class*='title'], [class*='header'] strong"
        )
        for el in candidates:
            txt = el.text.strip()
            if txt and len(txt) > 3 and "." in txt and not txt.startswith("$") and not any(c.isdigit() for c in txt[:4]):
                result["Website Name"] = txt
                break

        if result["Website Name"] == "N/A":
            # Fallback: look for first big text in modal
            try:
                result["Website Name"] = driver.find_element(
                    By.CSS_SELECTOR, ".ReactModalPortal [class*='title'], .ReactModalPortal h2, .ReactModalPortal p"
                ).text.strip()
            except:
                pass

        # ── Organic Traffic (look for visits / traffic number with K/M/B) ─────
        traffic_candidates = driver.find_elements(By.XPATH,
            "//*[contains(text(),'K') or contains(text(),'M') or contains(text(),'B') or contains(text(),'visits') or contains(text(),'traffic')]"
        )

        for el in traffic_candidates:
            txt = el.text.strip()
            if any(suffix in txt.lower() for suffix in ["k", "m", "b", " visits", " traffic"]):
                # Usually the first big number near "organic" or standalone is it
                if "organic" in el.get_attribute("outerHTML").lower() or "search" in el.get_attribute("outerHTML").lower():
                    result["Organic Traffic"] = txt
                    break
                elif result["Organic Traffic"] == "N/A" and any(c in txt for c in "KM"):
                    result["Organic Traffic"] = txt  # best guess

        # ── Traffic Worth ($) ────────────────────────────────────────────────
        worth_candidates = driver.find_elements(By.XPATH,
            "//*[contains(text(),'$')]"
        )
        for el in worth_candidates:
            txt = el.text.strip()
            if txt.startswith("$") and any(c.isdigit() for c in txt):
                # Usually the biggest / first one near "worth" or "value"
                parent_html = el.find_element(By.XPATH, "..").get_attribute("outerHTML").lower()
                if any(w in parent_html for w in ["worth", "value", "traffic value", "usd"]):
                    result["Traffic Worth"] = txt
                    break
                elif result["Traffic Worth"] == "N/A":
                    result["Traffic Worth"] = txt  # fallback

        # ── Final decision ───────────────────────────────────────────────────
        has_data = any(x != "N/A" for x in [result["Website Name"], result["Organic Traffic"], result["Traffic Worth"]])

        if has_data:
            result["Status"] = "Success"
            result["Debug"] += " | Data extracted"
        else:
            result["Status"] = "No data found"
            result["Debug"] += " | Found container but could not match numbers/names"

    except Exception as e:
        result["Status"] = "Error"
        result["Debug"] = f"Exception: {str(e)[:180]}…"

    return result
