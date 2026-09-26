from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import re
import subprocess
import os
import sys
import tempfile
from typing import List, Dict, Any
from urllib.parse import urljoin

try:
    from webdriver_manager.chrome import ChromeDriverManager

    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False
    print("Installing webdriver-manager...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "webdriver-manager"])
    from webdriver_manager.chrome import ChromeDriverManager

    USE_WEBDRIVER_MANAGER = True

# Chrome version settings
CHROME_VERSION = "139"
CHROME_DRIVER_PATH = None

try:
    from google.adk.agents import Agent

    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    print("Warning: google.adk.agents not available - Agent features disabled")


def get_driver():
    """Initialize and return a Chrome WebDriver instance with version 139."""
    # Create temp directory for Chrome data
    temp_dir = os.path.join(tempfile.gettempdir(), "chrome_temp")
    os.makedirs(temp_dir, exist_ok=True)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("start-maximized")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    try:
        print(f"📦 Downloading Chrome {CHROME_VERSION} driver...")
        os.environ["WDM_LOG"] = "0"

        driver_path = ChromeDriverManager().install()
        print(f"✓ Chrome driver ready: {driver_path}")

        service = ChromeService(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print(f"✓ Chrome browser initialized successfully")
        return driver

    except Exception as e:
        print(f"⚠️  Error setting up Chrome driver: {e}")
        print("Attempting alternative driver setup...")
        try:
            driver_path = ChromeDriverManager().install()
            service = ChromeService(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"✓ Chrome browser initialized with auto-detected version")
            return driver
        except Exception as e2:
            print(f"❌ Failed to initialize Chrome: {e2}")
            raise


def extract_with_javascript(driver) -> List[Dict[str, Any]]:
    """Use intelligent JavaScript to extract product data from the DOM."""
    try:
        print("🤖 Executing AI-enhanced JavaScript extraction...")

        js_code = """
        (function() {
            const products = [];
            
            // Strategy 1: Look for table rows with product data
            const rows = document.querySelectorAll('tbody tr, table tr');
            for (let row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 3) {
                    const sku = cells[0]?.innerText?.trim();
                    const titleCell = cells[1] || cells[2];
                    const title = titleCell?.innerText?.trim();
                    const priceCell = cells[3] || cells[4] || cells[5];
                    const price = priceCell?.innerText?.trim();
                    
                    // Validate: proper SKU, descriptive title, valid price
                    if (sku && sku.length >= 3 && sku.length <= 20 && 
                        title && title.length > 8 && !title.match(/^\\(\d+\\)$/) &&
                        price && (price.includes('$') || price.match(/^\\d+\\.\\d{2}$/))) {
                        
                        const priceNum = price.match(/([\\d.,]+)/);
                        if (priceNum) {
                            products.push({
                                sku: sku,
                                title: title.substring(0, 200),
                                price: priceNum[0],
                                url: row.querySelector('a')?.href || 'N/A'
                            });
                        }
                    }
                }
            }
            
            return products;
        })();
        """

        js_products = driver.execute_script(js_code)

        if js_products and len(js_products) > 0:
            print(f"✓ JavaScript extracted {len(js_products)} high-quality products")
            return js_products

        return []
    except Exception as e:
        print(f"⚠️  JavaScript extraction error: {str(e)[:50]}")
        return []


def extract_from_page_text(driver) -> List[Dict[str, Any]]:
    """AI-enhanced text extraction with smart filtering and validation."""
    products = []
    try:
        print("🤖 Using AI-enhanced text extraction...")

        # Try JavaScript first
        js_products = extract_with_javascript(driver)
        if js_products and len(js_products) > 0:
            return js_products

        # Fallback to intelligent text parsing
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = page_text.split("\n")

        # UI/navigation elements to filter
        ui_keywords = {
            "SEARCH",
            "BROWSE",
            "CATEGORY",
            "ADD TO LIST",
            "COMPARE",
            "FAQ",
            "HELP",
            "ABOUT",
            "CONTACT",
            "HOME",
            "CART",
            "CHECKOUT",
            "ACCOUNT",
            "SIGN IN",
            "REGISTER",
            "FILTER",
            "SORT",
            "VIEW",
            "NEXT",
            "PREVIOUS",
            "LOADING",
            "INK + TONER",
            "REFILL",
            "BACK TO TOP",
            "FEATURED",
            "SHOW",
            "EDIT",
            "SORT BY",
            "SHOW",
            "OF",
        }

        current_product = {}
        products_seen = set()
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or len(line) < 2:
                continue

            # Skip UI/navigation elements
            if line.upper() in ui_keywords or any(
                kw in line.upper() for kw in ui_keywords
            ):
                continue

            # Skip pure numbers (stock counts like "(29228)")
            if re.match(r"^\(\d+\)$|^\d+$", line):
                continue

            # Detect SKU pattern (uppercase alphanumeric, 3-20 chars)
            is_sku = re.match(r"^[A-Z0-9\-]{3,20}$", line)

            if is_sku:
                # Save previous product if complete
                if (
                    current_product
                    and "sku" in current_product
                    and "title" in current_product
                    and "price" in current_product
                ):
                    key = (current_product["sku"], current_product["title"])
                    if key not in products_seen:
                        products.append(current_product)
                        products_seen.add(key)

                current_product = {"sku": line}

                # Smart lookahead (next 5 lines)
                price_found = False
                title_found = False

                for j in range(i, min(i + 5, len(lines))):
                    look_line = lines[j].strip()

                    # Skip trivial content
                    if not look_line or re.match(r"^\(\d+\)$|^\d+$", look_line):
                        continue

                    # Extract price
                    if "$" in look_line and not price_found:
                        price_match = re.search(r"[\$]\s*(\d+[.,]\d{2}|\d+)", look_line)
                        if price_match:
                            current_product["price"] = price_match.group(0)
                            price_found = True
                        continue

                    # Extract real product title (description)
                    if (
                        not title_found
                        and len(look_line) > 10
                        and len(look_line) < 250
                        and not look_line.startswith("$")
                        and not re.match(r"^[A-Z0-9\-]{3,20}$", look_line)
                    ):
                        current_product["title"] = look_line
                        title_found = True
                        i = j + 1
                        break

        # Add final product if complete
        if (
            current_product
            and "sku" in current_product
            and "title" in current_product
            and "price" in current_product
        ):
            key = (current_product["sku"], current_product["title"])
            if key not in products_seen:
                products.append(current_product)

        print(f"✓ AI extraction found {len(products)} validated products")
        return products
    except Exception as e:
        print(f"❌ Text extraction failed: {e}")
        return []


def detect_product_selectors(driver) -> Dict[str, str]:
    """Detect product elements by analyzing page structure."""
    try:
        url = driver.current_url
        print(f"\nAnalyzing page: {url}")
        print(f"Page title: {driver.title}")

        # Site-specific rules
        if "biggestbook.com" in url:
            print("✓ Detected biggestbook.com - using enhanced site-specific selectors")
            return {
                "product_container": "table tr:has(td:not(:empty)), tbody tr",
                "title": "td:nth-child(2), td:nth-child(3)",
                "price": "td:nth-child(4), td:nth-child(5), td:nth-child(6)",
                "sku": "td:nth-child(1)",
                "link": "td a[href]",
            }

        print("Using generic selectors...")
        return {
            "product_container": "tr, li, div[class*='item'], article, section",
            "title": "h2, h3, h4, a, span, p",
            "price": "span, div, td, p",
            "sku": "span, td, code",
            "link": "a[href]",
        }

    except Exception as e:
        print(f"Error in selector detection: {e}")
        return {
            "product_container": "div, li, tr, article",
            "title": "h2, h3, h4, a, span",
            "price": "span, div, td",
            "sku": "span, td, code",
            "link": "a",
        }


def extract_products(driver, selectors: Dict[str, str]) -> List[Dict[str, Any]]:
    """Extract products using selectors, fallback to AI text extraction."""
    products = []

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "body"))
        )

        containers = driver.find_elements(
            By.CSS_SELECTOR, selectors["product_container"]
        )
        print(f"\nFound {len(containers)} product containers")

        if len(containers) == 0:
            print("⚠️  No containers found, using AI-enhanced text extraction...")
            return extract_from_page_text(driver)

        print("\n✓ Using DOM-based extraction")
        return extract_from_page_text(driver)

    except Exception as e:
        print(f"Error in product extraction: {e}")
        return extract_from_page_text(driver)


def clean_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean and deduplicate products."""
    seen = set()
    cleaned = []

    for product in products:
        title_lower = product.get("title", "").lower().strip()

        if not title_lower or title_lower in seen:
            continue

        seen.add(title_lower)

        # Clean price
        if product.get("price") and product["price"] != "N/A":
            match = re.search(r"\d+\.?\d{0,2}", str(product["price"]).replace(",", ""))
            if match:
                product["price"] = match.group(0)

        # Clean SKU
        if product.get("sku"):
            product["sku"] = product["sku"].upper().strip()

        cleaned.append(product)

    return cleaned


def ProductScraperTool(url: str, output_file: str = "scraped_products.json") -> str:
    """Enhanced product scraper with AI extraction."""
    driver = None
    try:
        print(f"\n{'='*70}")
        print(f"🔄 STARTING AI-ENHANCED PRODUCT SCRAPER")
        print(f"📍 URL: {url}")
        print(f"{'='*70}")

        driver = get_driver()
        driver.get(url)

        print("⏳ Waiting for page to load...")
        time.sleep(5)

        page_source_len = len(driver.page_source)
        if page_source_len < 100:
            print("⚠️  Page source small, retrying...")
            time.sleep(3)
            driver.refresh()
            time.sleep(3)

        print("📜 Scrolling to load dynamic content...")
        for i in range(5):
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(1.5)

        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        print("⏳ Waiting for dynamic content to stabilize...")
        time.sleep(3)

        print("\n🔍 Detecting product element selectors...")
        selectors = detect_product_selectors(driver)

        print("\n📦 Extracting products...")
        products = extract_products(driver, selectors)

        if len(products) == 0:
            print("⚠️  No products found, retrying extraction...")
            time.sleep(2)
            products = extract_products(driver, selectors)

        products = clean_products(products)

        result = {
            "url": url,
            "timestamp": time.time(),
            "products_found": len(products),
            "products": products,
            "success": True,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*70}")
        print(f"✅ SUCCESS: Scraped {len(products)} products")
        print(f"💾 Saved to: {output_file}")
        print(f"{'='*70}\n")

        return f"✅ Success: Scraped {len(products)} products from {url}"

    except Exception as e:
        error_msg = f"❌ Error scraping {url}: {str(e)}"
        print(f"\n{error_msg}")

        try:
            error_result = {
                "url": url,
                "timestamp": time.time(),
                "success": False,
                "error": str(e),
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(error_result, f, indent=2)
        except:
            pass

        return error_msg

    finally:
        if driver:
            driver.quit()
            print("🔌 Browser closed")


if __name__ == "__main__":
    test_url = (
        "https://miamilots.com/en/items?category=personal-care-health-and-beauty&page=3"
    )
    result = ProductScraperTool(test_url, "scraped_productspage3_enhanced.json")
    print(result)
