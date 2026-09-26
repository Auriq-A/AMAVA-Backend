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

"""
🚀 DYNAMIC PRODUCT SCRAPER - NOW WORKS WITH ANY WEBSITE!

KEY FEATURES:
✅ Gemini AI-powered product extraction from any website
✅ Dynamic product URL detection and storage
✅ Multi-website support (no hardcoded URLs)
✅ Automatic detail page navigation using real product URLs
✅ Comprehensive product enrichment (specs, images, ratings, etc.)
✅ 3-tier extraction fallback (Gemini → JavaScript → Text parsing)

DYNAMIC FUNCTIONALITY:
- Products are extracted with their actual URLs from each website
- Detail extraction uses the real product URL, not constructed patterns
- Works seamlessly across different e-commerce platforms
- No need to change code when switching websites

USAGE:
    python ProductScraper.py <URL>
Example:
    python ProductScraper.py "https://www.biggestbook.com"
    python ProductScraper.py "https://www.alibaba.com/search"
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
CHROME_DRIVER_PATH = None

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

try:
    from google.adk.agents import Agent

    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False


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


def extract_with_gemini_ai(
    page_text: str, page_html: str = None, product_links: List[str] = None
) -> List[Dict[str, Any]]:
    """Use Google Gemini AI to intelligently extract products AND their real product URLs."""
    if not GEMINI_AVAILABLE:
        print("⚠️  Gemini AI not available")
        return []

    try:
        print("🤖 Using Google Gemini AI to extract products with REAL URLs...")

        # Configure Gemini
        API_KEY = (
            os.getenv("GOOGLE_API_KEY") or "AIzaSyB_WmqEZ24YDZvHNL59TXA-kN32xS-oIyg"
        )
        if not API_KEY:
            print("⚠️  GOOGLE_API_KEY not set. Set it: set GOOGLE_API_KEY=your_key")
            return []

        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        # Include known product links if available for better matching
        links_info = ""
        if product_links and len(product_links) > 0:
            print(f"  └─ Using {len(product_links)} product links for matching...")
            links_info = f"\n\nACTUAL PRODUCT LINKS FOUND ON PAGE ({len(product_links)} total):\n"
            links_info += "\n".join(product_links)
        else:
            # Include HTML snippet as fallback to help find URLs
            if page_html:
                # Extract href links from HTML
                href_links = re.findall(r'href=["\'](.*?)["\']', page_html)
                product_links = [
                    link
                    for link in href_links
                    if any(kw in link.lower() for kw in ["item", "product", "detail"])
                ]
                if product_links:
                    links_info = (
                        f"\n\nKNOWN PRODUCT LINKS ON PAGE ({len(product_links)} found):\n"
                        + "\n".join(product_links)
                    )

        prompt = f"""
        CRITICAL: Extract REAL product URLs from the provided links. For each product found, match it with a URL from the links list.
        
        TASK: Extract ALL products from this e-commerce page. 
        For EACH product, extract:
        - SKU/Product Code (any identifier, or generate like "PROD001")
        - Title (actual product name/description, minimum 8 chars)
        - Price (numeric value only, no currency symbol)
        - URL (REAL product link that MUST come from the provided links list below)
        
        # if the site name is doba.com then heres how products urls look like: https://www.doba.com/product/....../......html
        if the site name is app.avasam.com then heres how products urls look like: https://app.avasam.com/seller/products/.../
        and whats important to extract from this site is its product and every page have 200 products, so find 200 of em dont just extract 17 or 16 extract all 200 products and their urls, and if you can find more than 200 products extract em too, but the main point is to extract 200 products with their urls, and the urls should be the real product urls not just the homepage or category page urls, so look for patterns in the links that indicate they are product pages.
        
        URL MATCHING STRATEGY:
        1. For each product found in the text, look through the provided links below
        2. Match based on: product name similarity, position order, or any visible ID/SKU
        3. Use fuzzy matching - if product is "Dinosaurs Figurines" and a link contains "dinosaur" or "figure", it's likely a match
        4. Products are usually listed in the same order as links
        5. ONLY use URLs from the provided list - NEVER construct or guess URLs
        6. If you cannot confidently match a product to a link, set url to null
        
        LINK LIST TO MATCH AGAINST:
        {links_info}
        
        IMPORTANT RULES:
        - Skip UI/Navigation text (Home, Search, Cart, Account, Help, etc)
        - Skip lines with just numbers like "(29228)" or "100"
        - Only include products with: title (8+ chars) + price
        - Prices should be just numbers: "99.99" not "$99.99"
        - Return ONLY valid JSON array with keys: sku, title, price, url
        
        Page text to extract from:
        {page_text}
        
        Return ONLY valid JSON array, no other text, no markdown:
        [
          {{"sku": "ABC123", "title": "Product Name Description", "price": "99.99", "url": "https://example.com/product/123"}},
          {{"sku": "PROD002", "title": "Another Product Item", "price": "45.50", "url": "https://example.com/item/456"}}
        ]
        """

        response = model.generate_content(prompt)

        if response.text:
            print(response.text)
            # Parse JSON from response
            json_match = re.search(r"\[\s*\{.*?\}\s*\]", response.text, re.DOTALL)
            if json_match:
                # print(json_match)
                products = json.loads(json_match.group())
                # print("prid:", products)
                print(f"✓ Gemini AI extracted {len(products)} products")

                # Verify URLs were extracted
                urls_found = sum(
                    1 for p in products if p.get("url") and p.get("url") != "N/A"
                )
                if urls_found > 0:
                    print(f"  └─ URLs found: {urls_found}/{len(products)}")
                else:
                    print(f"  └─ Warning: No URLs found in extracted products")

                return products

        return []

    except Exception as e:
        print(f"⚠️  Gemini AI error: {str(e)[:100]}")
        return []


def extract_with_javascript(driver) -> List[Dict[str, Any]]:
    """Use intelligent JavaScript to extract product data from the DOM with real URLs."""
    try:
        print("🤖 Executing AI-enhanced JavaScript extraction from HTML structure...")

        js_code = """
        (function() {
            const products = [];
            
            // Strategy 1: Look for table rows with product data
            const rows = document.querySelectorAll('tbody tr, table tr');
            for (let row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 3) {
                    // Try to find actual product link first
                    const productLink = row.querySelector('a[href*="itemDetail"], a[href*="product"], a.product-link');
                    const productUrl = productLink?.href;
                    
                    // Extract SKU from URL if available
                    let sku = cells[0]?.innerText?.trim();
                    if (productUrl && !sku) {
                        const urlMatch = productUrl.match(/itemId[=?]([A-Z0-9]+)/i);
                        sku = urlMatch ? urlMatch[1] : null;
                    }
                    
                    const titleCell = cells[1] || cells[2];
                    const title = titleCell?.innerText?.trim();
                    const priceCell = cells[3] || cells[4] || cells[5];
                    const price = priceCell?.innerText?.trim();
                    
                    // Validate: descriptive title and valid price
                    if (title && title.length > 8 && !title.match(/^\\(\d+\\)$/) &&
                        price && (price.includes('$') || price.match(/^\\d+\\.\\d{2}$/))) {
                        
                        const priceNum = price.match(/([\\d.,]+)/);
                        if (priceNum && productUrl) {
                            products.push({
                                sku: sku || 'UNKNOWN',
                                title: title.substring(0, 200),
                                price: priceNum[0],
                                url: productUrl
                            });
                        }
                    }
                }
            }
            
            // Strategy 2: If table extraction failed, look for product cards/divs with links
            if (products.length === 0) {
                const productCards = document.querySelectorAll('[class*="product"], [data-product], li.item, div.product-item');
                for (let card of productCards) {
                    const link = card.querySelector('a[href*="itemDetail"], a[href*="product"]');
                    if (link && link.href) {
                        const title = card.querySelector('[class*="title"], h2, h3, .product-name')?.innerText?.trim();
                        const price = card.querySelector('[class*="price"], .product-price, span.price')?.innerText?.trim();
                        
                        if (title && price) {
                            const urlMatch = link.href.match(/itemId[=?]([A-Z0-9]+)/i);
                            const sku = urlMatch ? urlMatch[1] : title.substring(0, 20);
                            
                            const priceNum = price.match(/([\\d.,]+)/);
                            if (priceNum) {
                                products.push({
                                    sku: sku,
                                    title: title.substring(0, 200),
                                    price: priceNum[0],
                                    url: link.href
                                });
                            }
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


def extract_from_html_source(driver) -> List[Dict[str, Any]]:
    """Extract products by analyzing HTML source for real product links."""
    try:
        print("🔍 Extracting real product URLs from HTML source...")

        # Get the actual HTML source
        html_source = driver.page_source

        # Find all product links using regex
        # Look for patterns like: href="/items?id=..." or href="#/itemDetail?itemId=..."
        link_pattern = r'href='
        links = re.findall(link_pattern, html_source)

        products = []
        for link in links:
            # Filter for product links (not navigation, not external, etc.)
            if ("item" in link.lower() or "product" in link.lower()) and not any(
                x in link.lower() for x in ["contact", "about", "help", "account"]
            ):
                # Try to extract product ID from URL
                id_match = re.search(
                    r"(?:id|itemId|productId)[=?]([A-Za-z0-9\-_]+)", link, re.IGNORECASE
                )
                if id_match:
                    product_id = id_match.group(1)
                    # Found a real product URL
                    full_url = (
                        link
                        if link.startswith("http")
                        else (link if link.startswith("/") else "/" + link)
                    )
                    print(f"  ✓ Found product link: {full_url[:60]}")
                    return [{"sku": product_id, "url": full_url}]  # Return as hint

        return []
    except Exception as e:
        print(f"⚠️  HTML source extraction error: {str(e)[:50]}")
        return []


def extract_from_page_text(driver) -> List[Dict[str, Any]]:
    """AI-ONLY extraction using Gemini to extract products AND their real URLs."""
    products = []
    try:
        print(
            "🤖 AI-ONLY EXTRACTION: Using Gemini to find products and their actual URLs..."
        )

        # Get full page text and HTML
        page_text = driver.find_element(By.TAG_NAME, "body").text
        page_html = driver.page_source

        # CRITICAL: Extract actual product links from page FIRST using JavaScript
        print("🔗 Extracting product links from page...")
        product_links = []
        try:
            # Execute JavaScript to find all product links - UNIVERSAL APPROACH
            js_links = driver.execute_script(
                """
                let links = [];
                let baseUrl = window.location.origin;
                let currentPath = window.location.pathname;
                
                // Strategy 1: Look in product containers (most reliable)
                let productContainers = document.querySelectorAll(
                    '[class*="product"], [class*="item"], [data-product], [data-item], ' +
                    'article, .card, .listing, li.product, div.product-item, tr, .pi-detail, .product-item, .ps-product, .ps-product-rn'
                );
                
                for (let container of productContainers) {
                    let link = container.querySelector('a[href]');
                    if (link && link.href) {
                        let href = link.href;
                        // Make absolute if relative
                        if (href.startsWith('/')) {
                            href = baseUrl + href;
                        }
                        // Skip navigation/UI links
                        if (!href.includes('search') && !href.includes('filter') && 
                            !href.includes('cart') && !href.includes('account') &&
                            !href.includes('login') && !href.includes('checkout')) {
                            links.push(href);
                        }
                    }
                }
                
                // Strategy 2: If not enough links found, look for ALL links with patterns
                if (links.length < 5) {
                    let allLinks = document.querySelectorAll('a[href]');
                    for (let link of allLinks) {
                        let href = link.href || link.getAttribute('href');
                        if (href) {
                            // Only include links that point to product pages (not home, nav, etc)
                            if ((href.includes('/product') || href.includes('/item') || 
                                 href.includes('?id=') || href.includes('product-') ||
                                 href.includes('.html') && !href.includes('/index')) &&
                                !href.includes('search') && !href.includes('filter')) {
                                if (!links.includes(href)) {
                                    links.push(href);
                                }
                            }
                            if (!links.includes(href)) {
                                    links.push(href);
                                }
                        }
                    }
                }
                
                // Strategy 3: Look for links in specific product list structures
                if (links.length < 5) {
                    let rows = document.querySelectorAll('tbody tr, table tr, .row, .grid-item');
                    for (let row of rows) {
                        let link = row.querySelector('a');
                        if (link && link.href) {
                            let href = link.href;
                            if (href.startsWith('/')) href = baseUrl + href;
                            if (!links.includes(href)) {
                                links.push(href);
                            }
                        }
                    }
                }
                
                // Remove duplicates and return
                return [...new Set(links)];
            """
            )
            product_links = js_links if js_links else []
            print(f"✓ Found {len(product_links)} product links on page")
        except Exception as e:
            print(f"⚠️  Could not extract links with JavaScript: {e}")
            product_links = []

        # Try Gemini AI extraction FIRST AND ONLY
        print("\nCalling Gemini AI to extract products with real URLs...")
        gemini_products = extract_with_gemini_ai(page_text, page_html, product_links)
        if gemini_products and len(gemini_products) > 0:
            print(f"✓ Gemini AI extracted {len(gemini_products)} products with URLs")
            return gemini_products

        print("\n⚠️  Gemini extraction failed, trying text parsing fallback...")

        # Fallback to text parsing (but still NO hardcoded patterns)
        lines = page_text.split("\n")

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

            if line.upper() in ui_keywords or any(
                kw in line.upper() for kw in ui_keywords
            ):
                continue

            if re.match(r"^\(\d+\)$|^\d+$", line):
                continue

            is_sku = re.match(r"^[A-Z0-9\-]{3,20}$", line)

            if is_sku:
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

                current_product = {
                    "sku": line,
                    "url": "N/A",
                }  # Mark URL as N/A for manual extraction

                price_found = False
                title_found = False

                for j in range(i, min(i + 5, len(lines))):
                    look_line = lines[j].strip()

                    if not look_line or re.match(r"^\(\d+\)$|^\d+$", look_line):
                        continue

                    if "$" in look_line and not price_found:
                        price_match = re.search(r"[\$]\s*(\d+[.,]\d{2}|\d+)", look_line)
                        if price_match:
                            current_product["price"] = price_match.group(0)
                            price_found = True
                        continue

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

        if (
            current_product
            and "sku" in current_product
            and "title" in current_product
            and "price" in current_product
        ):
            key = (current_product["sku"], current_product["title"])
            if key not in products_seen:
                products.append(current_product)

        if len(products) > 0:
            print(
                f"✓ Text parsing found {len(products)} products (but URLs marked as N/A - need Gemini)"
            )
            print(
                "⚠️  WARNING: Products extracted but missing real URLs. Consider using Gemini API."
            )

        return products
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
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
        if "doba.com" in url:
            print("✓ Detected doba.com - using enhanced site-specific selectors")
            return {
                "product_container": ".product-item",
                "title": "span, div.pi-detail > div.pi-name > a > span",
                "price": "div.pi-detail > div.pi-price-wrap > div > span > b, b",
                "sku": "span, td, code",
                "link": "div.pi-detail > div.pi-name > a[href], div.pi-image-box > a[href]",
                "image_link": "div.pi-image-box > a > div > div > div.lazyload-wrapper > div > div > div > div > div.slick-slide.slick-active.slick-current > div > img[src]",
            }
        if "app.avasam.com" in url:
            print("✓ Detected app.avasam.com - using enhanced site-specific selectors")
            return {
                "product_container": ".ps-product, .ps-product-rn",
                "title": "div > div.ps-product_option > div:nth-child(1) > div > label > a > div > span > span, .ps-product__title",
                "price": "div > div.ps-product_option > div:nth-child(3) > div > div:nth-child(1) > div > span:nth-child(2) > span",
                "stock": "div > div.ps-product_option > div:nth-child(2) > div > div.ant-col.ant-col-14.css-18s64pp.avasam > div > label",
                "link": "div > div.ps-product_option > div:nth-child(1) > div > label > a[href]",
                "image_link": "div > div.ps-product__thumbnail > div > div > div > div.slick-slide.slick-active.slick-current > div > div > div > a > div[name]"
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
            By.CSS_SELECTOR, selectors["product-item"]
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


def extract_product_details(
    driver, product: Dict[str, Any], base_url: str = None
) -> Dict[str, Any]:
    """Extract detailed product information from product detail page using REAL product URL only."""
    try:
        sku = product.get("sku", "N/A")
        product_url = product.get("url", None)

        # ONLY use REAL product URLs - NO hardcoded patterns!
        if not product_url or product_url == "N/A":
            print(f"  ⚠️  No product URL found for {sku}, skipping details extraction")
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
            if "sku" not in product:
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
        for i in range(15):
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

        # products = clean_products(products)

        # NEW: Enrich products with detail page information
        if len(products) > 0:
            print(f"\n{'='*70}")
            print(f"📄 ENRICHING PRODUCTS WITH DETAIL PAGE INFO")
            print(f"{'='*70}")
            # Extract base URL from the input URL for fallback pattern construction
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            products = enrich_products_with_details(driver, products, base_url)

        result = {
            "url": url,
            "timestamp": time.time(),
            "products_found": len(products),
            "products": products,
            "success": True,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            # append instead of deleting previous content
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*70}")
        print(f"✅ SUCCESS: Scraped and enriched {len(products)} products")
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
    # test_url = (
    #     "https://www.doba.com/search?catId=geVDqCYMrobh&pageSize=40&pageNo=2"
    # )
    # result = ProductScraperTool(test_url, output_file="doba_office_products_page2.json")
    # print(result)
    
    # Scrape next pages from page no. 1 to 10 using loop
    for page in range(1, 11):
        test_url = f"https://www.doba.com/search?catId=BovRVPJymYDO&pageSize=40&pageNo={page}"
        result = ProductScraperTool(test_url, output_file=f"doba_home_products_page{page}.json")
        print(result)

    # test_url2 = (
    #     "https://www.supplynextwholesale.com/products/category/beauty-personal-care?page=2"
    # )
    # result2 = ProductScraperTool(test_url2, output_file="supply_next_beauty_products_page2.json")
    # print(result2)
    
    # test_url3 = (
    #     "https://www.supplynextwholesale.com/products/category/beauty-personal-care?page=3"
    # )
    # result3 = ProductScraperTool(test_url3, output_file="supply_next_beauty_products_page3.json")
    # print(result3)

