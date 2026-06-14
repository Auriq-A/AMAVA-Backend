from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import json
import re
import subprocess
import os
import sys
import tempfile
from typing import List, Dict, Any
from urllib.parse import urljoin

"""
🚀 AVASAM DEDICATED PRODUCT SCRAPER

KEY FEATURES:
✅ Gemini AI-powered product extraction optimized for Avasam
✅ Direct product URL extraction from Avasam's DOM structure
✅ Automatic detail page navigation using real product URLs
✅ Comprehensive product enrichment (specs, images, ratings, etc.)
✅ Avasam-specific HTML parsing and selectors

AVASAM-SPECIFIC:
- Uses Avasam's .ps-product* class structure
- Extracts product URLs from Avasam's href patterns
- Handles Avasam's pagination and product loading
- Optimized for app.avasam.com seller products

USAGE:
    python ProductScraperAvasam.py
    
Example:
    Scrapes from: https://app.avasam.com/seller/product/search/
"""

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

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Installing Google Gemini AI...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "google-generativeai"]
        )
        import google.generativeai as genai

        GEMINI_AVAILABLE = True
    except:
        print("Warning: Google Gemini AI not available")


def get_driver():
    """Initialize and return a Chrome WebDriver instance with version 139."""
    # Create temp directory for Chrome data
    temp_dir = os.path.join(tempfile.gettempdir(), "Avasam_Chrome")
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
        driver.set_page_load_timeout(180)
        driver.set_script_timeout(180)
        driver.implicitly_wait(10)
        print(f"✓ Chrome browser initialized successfully")
        return driver

    except Exception as e:
        print(f"⚠️  Error setting up Chrome driver: {e}")
        print("Attempting alternative driver setup...")
        try:
            driver_path = ChromeDriverManager().install()
            service = ChromeService(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(180)
            driver.set_script_timeout(180)
            driver.implicitly_wait(10)
            print(f"✓ Chrome browser initialized with auto-detected version")
            return driver
        except Exception as e2:
            print(f"❌ Failed to initialize Chrome: {e2}")
            raise


def extract_with_gemini_ai(
    page_text: str, page_html: str = None, product_links: List[str] = None
) -> List[Dict[str, Any]]:
    """Use Google Gemini AI to extract products from Avasam with real URLs."""
    if not GEMINI_AVAILABLE:
        print("⚠️  Gemini AI not available")
        return []

    try:
        print("🤖 Using Google Gemini AI to extract Avasam products...")

        # Configure Gemini
        API_KEY = (
            os.getenv("GOOGLE_API_KEY") or "AIzaSyB_WmqEZ24YDZvHNL59TXA-kN32xS-oIyg"
        )
        if not API_KEY:
            print("⚠️  GOOGLE_API_KEY not set")
            return []

        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        # Build links info for Gemini
        links_info = ""
        if product_links and len(product_links) > 0:
            print(f"  └─ Using {len(product_links)} product links for matching...")
            links_info = f"\n\nAVASAM PRODUCT LINKS FOUND ({len(product_links)} total):\n"
            links_info += "\n".join(product_links[:300])  # Limit to 300 links

        prompt = f"""
        TASK: Extract ALL products from this Avasam marketplace page.
        
        For EACH product, extract:
        - stock: Product ID (from URL pattern: https://app.avasam.com/seller/products/XXXXX/)
        - title: Actual product name/description (minimum 8 characters)
        - price: Numeric value only (e.g., "99.99", not "$99.99")
        - url: REAL product link matching the pattern https://app.avasam.com/seller/products/[ID]/
        - image: Product image URL if available
        
        AVASAM-SPECIFIC RULES:
        - Products on Avasam typically show 200 per page
        - Product IDs are alphanumeric codes in the URL
        - Extract ALL visible products, not just a subset
        - Price values should be clean numbers only
        - Only use product URLs from the provided links list
        
        URL MATCHING:
        - Match products by position and title similarity
        - Use ONLY URLs from the provided list below
        - If no match found, set url to null
        
        PRODUCT LINKS:
        {links_info}
        
        Page text:
        {page_text}
        
        Return ONLY valid JSON array:
        [
          {{"stock": "PROD123", "title": "Product Name Description", "price": "99.99", "url": "https://app.avasam.com/seller/products/PROD123/", "image": "https://..."}},
          {{"stock": "PROD124", "title": "Another Product", "price": "45.50", "url": "https://app.avasam.com/seller/products/PROD124/", "image": "https://..."}}
        ]
        """

        response = model.generate_content(prompt)

        if response.text:
            # Parse JSON from response
            json_match = re.search(r"\[\s*\{.*?\}\s*\]", response.text, re.DOTALL)
            if json_match:
                products = json.loads(json_match.group())
                print(f"✓ Gemini AI extracted {len(products)} products")

                # Verify URLs were extracted
                urls_found = sum(
                    1 for p in products if p.get("url") and p.get("url") != "N/A" and p.get("url") != "null"
                )
                print(f"  └─ URLs found: {urls_found}/{len(products)}")

                return products

        return []

    except Exception as e:
        print(f"⚠️  Gemini AI error: {str(e)[:100]}")
        return []


def extract_with_javascript(driver) -> List[Dict[str, Any]]:
    """Extract product data from Avasam's DOM structure using JavaScript."""
    try:
        print("🤖 Executing Avasam-specific JavaScript extraction...")

        js_code = """
        (function() {
            const products = [];
            let baseUrl = window.location.origin;
            
            // Target Avasam's product container structure
            const productContainers = document.querySelectorAll('.ps-product, .ps-product-rn');
            
            for (let container of productContainers) {
                try {
                    // Extract product link (contains the ID)
                    const productLink = container.querySelector('div > div.ps-product_option > div:nth-child(1) > div > label > a[href]');
                    if (!productLink || !productLink.href) continue;
                    
                    const productUrl = productLink.href;
                    
                    // Extract stock/ID from URL if available
                    const urlMatch = productUrl.match(/products\\/([A-Z0-9]+)/i);
                    let stock = urlMatch ? urlMatch[1] : 'UNKNOWN';
                    
                    // Extract title
                    const titleElem = container.querySelector('div > div.ps-product_option > div:nth-child(1) > div > label > a > div > span > span');
                    const title = titleElem?.innerText?.trim();
                    
                    // Extract price
                    const priceElem = container.querySelector('div > div.ps-product_option > div:nth-child(3) > div > div:nth-child(1) > div > span:nth-child(2) > span');
                    let price = priceElem?.innerText?.trim();
                    
                    // Extract image
                    const imageElem = container.querySelector('img[src]');
                    const image = imageElem?.src;
                    
                    // Validate required fields
                    if (!title || title.length < 8 || !price) continue;
                    
                    // Clean price - remove currency symbols and spaces
                    price = price.replace(/[^0-9.]/g, '').trim();
                    if (!price || isNaN(parseFloat(price))) continue;
                    
                    products.push({
                        stock: stock,
                        title: title.substring(0, 200),
                        price: price,
                        url: productUrl,
                        image: image || null
                    });
                } catch (e) {
                    console.log('Error processing product:', e);
                }
            }
            
            return products;
        })();
        """

        js_products = driver.execute_script(js_code)

        if js_products and len(js_products) > 0:
            print(f"✓ JavaScript extracted {len(js_products)} products from Avasam")
            return js_products

        return []
    except Exception as e:
        print(f"⚠️  JavaScript extraction error: {str(e)[:50]}")
        return []


def extract_product_links_from_page(driver) -> List[str]:
    """Extract all product links from Avasam page using JavaScript and HTML analysis."""
    try:
        print("🔗 Extracting product links from Avasam page...")
        product_links = []
        
        # Execute JavaScript to find Avasam product links
        js_links = driver.execute_script(
            """
            let links = [];
            let baseUrl = window.location.origin;
            
            // Strategy 1: Look in Avasam product containers
            let productContainers = document.querySelectorAll('.ps-product, .ps-product-rn');
            for (let container of productContainers) {
                let link = container.querySelector('a[href*="/seller/products/"]');
                if (link && link.href) {
                    let href = link.href;
                    if (!links.includes(href)) {
                        links.push(href);
                    }
                }
            }
            
            // Strategy 2: Look for all product links directly
            if (links.length < 50) {
                let allLinks = document.querySelectorAll('a[href*="/seller/products/"]');
                for (let link of allLinks) {
                    let href = link.href;
                    if (href && !links.includes(href)) {
                        links.push(href);
                    }
                }
            }
            
            // Remove duplicates and return
            return [...new Set(links)];
        """
        )
        
        product_links = js_links if js_links else []
        print(f"✓ Found {len(product_links)} product links on Avasam page")
        return product_links
        
    except Exception as e:
        print(f"⚠️  Error extracting product links: {e}")
        return []


def extract_from_page(driver) -> List[Dict[str, Any]]:
    """Extract products from Avasam page using JavaScript first, then Gemini AI."""
    products = []
    try:
        print("📦 Extracting products from Avasam page...")

        # Step 1: Try JavaScript extraction (fastest)
        print("\n1️⃣ Attempting JavaScript extraction...")
        js_products = extract_with_javascript(driver)
        
        if js_products and len(js_products) > 0:
            print(f"✓ JavaScript successfully extracted {len(js_products)} products")
            return js_products

        # Step 2: Fallback to Gemini AI extraction
        print("\n2️⃣ JavaScript returned no products, using Gemini AI extraction...")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        page_html = driver.page_source
        
        # Extract product links for Gemini to use
        product_links = extract_product_links_from_page(driver)
        
        gemini_products = extract_with_gemini_ai(page_text, page_html, product_links)
        if gemini_products and len(gemini_products) > 0:
            print(f"✓ Gemini AI extracted {len(gemini_products)} products")
            return gemini_products

        print("⚠️  No products extracted")
        return []

    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return []


def get_avasam_selectors() -> Dict[str, str]:
    """Return Avasam-specific CSS selectors for product extraction."""
    return {
        "product_container": ".ps-product, .ps-product-rn",
        "title": "div > div.ps-product_option > div:nth-child(1) > div > label > a > div > span > span, .ps-product__title",
        "price": "div > div.ps-product_option > div:nth-child(3) > div > div:nth-child(1) > div > span:nth-child(2) > span",
        "stock": "div > div.ps-product_option > div:nth-child(2) > div > div.ant-col.ant-col-14.css-18s64pp.avasam > div > label",
        "link": "div > div.ps-product_option > div:nth-child(1) > div > label > a[href]",
        "image_link": "div > div.ps-product__thumbnail > div > div > div > div.slick-slide.slick-active.slick-current > div > div > div > a > div[name]"
    }


def extract_products(driver) -> List[Dict[str, Any]]:
    """Extract products from Avasam page using optimized extraction pipeline."""
    try:
        print("⏳ Waiting for Avasam page to load...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "body"))
        )

        print("📦 Extracting products from Avasam...")
        products = extract_from_page(driver)

        if len(products) == 0:
            print("⚠️  No products found on first attempt, retrying extraction...")
            time.sleep(2)
            products = extract_from_page(driver)

        return products

    except Exception as e:
        print(f"Error in product extraction: {e}")
        return []


def extract_product_details(
    driver, product: Dict[str, Any], base_url: str = None
) -> Dict[str, Any]:
    """Extract detailed product information from product detail page using REAL product URL only."""
    try:
        stock = product.get("stock", "N/A")
        product_url = product.get("url", None)

        # ONLY use REAL product URLs - NO hardcoded patterns!
        if not product_url or product_url == "N/A":
            print(f"  ⚠️  No product URL found for {stock}, skipping details extraction")
            return {}

        print(f"  📄 Extracting details from: {product_url[:80]}")

        # Navigate to actual product page
        driver.get(product_url)
        time.sleep(3)  # Wait for page to load

        details = {}

        # Store the actual product URL
        details["product_url"] = product_url

        try:
            # Get all page text for pattern matching
            page_text = driver.find_element(By.TAG_NAME, "body").text

            # Extract UPC
            upc_match = re.search(
                r"(?:UPC|EAN)[:\s]+([0-9\-]{8,20})", page_text, re.IGNORECASE
            )
            if upc_match:
                details["upc"] = upc_match.group(1).strip()

            # Extract ASIN
            asin_match = re.search(
                r"(?:ASIN)[:\s]+([A-Z0-9]{10})", page_text, re.IGNORECASE
            )
            if asin_match:
                details["asin"] = asin_match.group(1).strip()

            # Extract MPN (Manufacturer Part Number)
            mpn_match = re.search(
                r"(?:MPN|Mfr\s+Part|Manufacturer\s+Part|Model)[:\s]+([A-Z0-9\-]{3,30})",
                page_text,
                re.IGNORECASE,
            )
            if mpn_match:
                details["mpn"] = mpn_match.group(1).strip()

            # Extract Brand
            brand_match = re.search(
                r"(?:Brand|Manufacturer)[:\s]+([A-Za-z0-9\s&™®]{3,50})",
                page_text,
                re.IGNORECASE,
            )
            if brand_match:
                details["brand"] = brand_match.group(1).strip()

            # Extract Weight
            weight_match = re.search(
                r"(?:Weight|Net Weight)[:\s]+([0-9.]+\s*(?:lb|lbs|kg|oz|g))",
                page_text,
                re.IGNORECASE,
            )
            if weight_match:
                details["weight"] = weight_match.group(1).strip()

            # Extract Dimensions
            dimension_match = re.search(
                r"(?:Dimension|Size|D x W x H)[:\s]+([0-9.\s\-x]+(?:in|cm|mm)?)",
                page_text,
                re.IGNORECASE,
            )
            if dimension_match:
                details["dimensions"] = dimension_match.group(1).strip()

            # Extract Color
            color_match = re.search(
                r"(?:Color|Colour)[:\s]+([A-Za-z\s0-9\-]+?)(?:\n|,|;|$)",
                page_text,
                re.IGNORECASE,
            )
            if color_match:
                color = color_match.group(1).strip()
                if len(color) < 50:  # Reasonable color length
                    details["color"] = color

            # Extract Quantity per unit
            qty_match = re.search(
                r"(?:Qty|Quantity|Count|Pack Size)[:\s]+(\d+)\s*(?:unit|pack|piece|count)?",
                page_text,
                re.IGNORECASE,
            )
            if qty_match:
                details["quantity_per_unit"] = qty_match.group(1)

        except:
            pass

        try:
            # Extract description
            desc_elem = driver.find_elements(By.TAG_NAME, "p")
            if desc_elem:
                full_desc = []
                for p in desc_elem[:3]:
                    text = p.text.strip()
                    if text and len(text) > 10:
                        full_desc.append(text)

                if full_desc:
                    details["description"] = " ".join(full_desc)[:800]
        except:
            pass

        try:
            # Extract specifications in a table
            specs = {}
            spec_rows = driver.find_elements(
                By.CSS_SELECTOR, "tr, .spec-item, [class*='spec']"
            )
            for row in spec_rows[:15]:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        spec_name = cells[0].text.strip()
                        spec_value = cells[1].text.strip()
                        if spec_name and spec_value and len(spec_name) < 50:
                            specs[spec_name] = spec_value
                except:
                    pass

            if specs:
                details["specifications"] = specs
        except:
            pass

            pass

        try:
            # Extract stock/inventory info
            page_text = driver.find_element(By.TAG_NAME, "body").text
            stock_match = re.search(
                r"(?:Stock|Qty|Quantity|Available|In Stock)[:\s]+(\d+)",
                page_text,
                re.IGNORECASE,
            )
            if stock_match:
                details["stock_available"] = int(stock_match.group(1))
        except:
            pass

        try:
            # Extract images
            images = []
            img_elements = driver.find_elements(
                By.CSS_SELECTOR,
                "img[src*='product'], img[alt*='product'], img[class*='product']",
            )
            for img in img_elements[:5]:
                src = img.get_attribute("src")
                if src and (src.startswith("http") or src.startswith("/")):
                    images.append(src)

            if images:
                details["images"] = list(set(images))  # Remove duplicates
        except:
            pass

        try:
            # Extract rating/reviews
            page_text = driver.find_element(By.TAG_NAME, "body").text
            rating_match = re.search(
                r"(?:Rating|Review|Stars)[:\s]+([0-9.]+)\s*(?:out of|/)?",
                page_text,
                re.IGNORECASE,
            )
            if rating_match:
                details["rating"] = float(rating_match.group(1))
        except:
            pass

        try:
            # Extract minimum order quantity
            page_text = driver.find_element(By.TAG_NAME, "body").text
            moq_match = re.search(
                r"(?:MOQ|Minimum Order|Min\s+Order)[:\s]+(\d+)",
                page_text,
                re.IGNORECASE,
            )
            if moq_match:
                details["minimum_order_qty"] = int(moq_match.group(1))
        except:
            pass

        extracted_fields = [k for k in details.keys() if k not in ["images"]]
        print(f"    ✓ Details extracted: {extracted_fields}")
        return details

    except Exception as e:
        print(f"    ⚠️  Error extracting details: {str(e)[:50]}")
        return {}


def enrich_products_with_details(
    driver, products: List[Dict[str, Any]], base_url: str = None
) -> List[Dict[str, Any]]:
    """Visit each product's detail page and extract additional information using actual product URLs or fallback patterns."""
    if not products or len(products) == 0:
        return products

    try:
        print(
            f"\n📄 Enriching {len(products)} products with detail page information..."
        )

        for idx, product in enumerate(products, 1):
            if "stock" not in product:
                continue

            print(
                f"\n[{idx}/{len(products)}] Processing {product.get('title', 'Unknown')[:50]}"
            )

            try:
                # Extract details from product page using the actual product URL (or fallback pattern)
                details = extract_product_details(driver, product, base_url)

                # Merge details into product
                product.update(details)

            except Exception as e:
                print(f"    Error processing product: {str(e)[:50]}")
                continue

        print(f"\n✓ Product enrichment complete")
        return products

    except Exception as e:
        print(f"Error in enrichment: {e}")
        return products


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

        # Clean stock
        if product.get("stock"):
            product["stock"] = product["stock"].upper().strip()

        cleaned.append(product)

    return cleaned


def ProductScraperTool(url: str, output_file: str = "scraped_products.json", login: str = None, login_required: bool = False, enrich_details: bool = True) -> str:
    """Avasam-dedicated product scraper with AI-enhanced extraction.
    
    Args:
        url: Avasam product page URL to scrape
        output_file: Output JSON file path (default: scraped_products.json)
        login: Login page URL (optional)
        login_required: Whether login is required (default: False)
        enrich_details: Whether to fetch product details from each product page (default: True)
    """
    driver = None
    try:
        # Validate URL is Avasam
        if "app.avasam.com" not in url:
            return "❌ Error: URL must be from app.avasam.com"

        print(f"\n{'='*70}")
        print(f"🔄 STARTING AVASAM PRODUCT SCRAPER")
        print(f"📍 URL: {url}")
        print(f"{'='*70}")

        driver = get_driver()
        
        # Handle login if required
        if login_required:
            print("📝 Navigating to login page...")
            driver.get(login)
            print("⏳ Please log in to Avasam within the browser window...")
            time.sleep(30)

        # Navigate to product page
        print(f"📄 Loading product page...")
        try:
            driver.get(url)
        except (TimeoutException, WebDriverException) as e:
            print(f"⚠️ Page load timeout: {e}")
            try:
                driver.execute_script("window.stop();")
            except:
                pass

        print("⏳ Waiting for page to load...")
        time.sleep(30)  # Wait for page to load and stabilize

        # Check if page loaded properly
        page_source_len = len(driver.page_source)
        if page_source_len < 100:
            print("⚠️  Page source too small, retrying...")
            time.sleep(3)
            driver.refresh()
            time.sleep(3)

        # Scroll to load dynamic content on Avasam
        print("📜 Scrolling to load all products...")
        last_height = driver.execute_script("return document.body.scrollHeight;")
        scroll_attempts = 0
        max_scrolls = 50
        
        while scroll_attempts < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight;")
            
            # if new_height == last_height:
            #     print(f"✓ Reached end of page after {scroll_attempts} scrolls")
            #     break
            last_height = new_height
            scroll_attempts += 1
            
            if scroll_attempts % 10 == 0:
                print(f"  Scrolled {scroll_attempts} times...")

        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        print("⏳ Waiting for page to stabilize...")
        time.sleep(3)

        # Extract products using Avasam-specific pipeline
        print("\n🔍 Extracting products using Avasam detection...")
        products = extract_products(driver)

        if len(products) == 0:
            print("⚠️  No products found on first extraction attempt, retrying...")
            time.sleep(2)
            products = extract_products(driver)

        # Enrich products with detail page information if URLs available and if enabled
        if len(products) > 0 and enrich_details:
            print(f"\n{'='*70}")
            print(f"📄 ENRICHING PRODUCTS WITH DETAIL PAGE INFO")
            print(f"{'='*70}")
            
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            products = enrich_products_with_details(driver, products, base_url)
        elif len(products) > 0 and not enrich_details:
            print(f"\n⏭️  Skipping product detail enrichment (disabled)")

        # Save results
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
        print(f"✅ SUCCESS: Scraped and enriched {len(products)} products")
        print(f"💾 Saved to: {output_file}")
        print(f"{'='*70}\n")

        return f"✅ Success: Scraped {len(products)} products from Avasam"

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
    # login first
    login_page = f"https://app.avasam.com/seller/sellerregister/login"
    
    # Configuration options
    ENRICH_PRODUCTS = False  # Set to False to skip fetching product details from detail pages
    
    # Scrape next pages from page no. 1 to 10 using loop

    test_url = f"https://app.avasam.com/seller/product/search?tag=37&echannel=Amazon&page=1"
    result = ProductScraperTool(test_url, output_file=f"avasam_office_products(50 scrolls).json", login=login_page, login_required=True, enrich_details=ENRICH_PRODUCTS)
    print(result)



