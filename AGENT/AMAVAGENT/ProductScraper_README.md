# ProductScraper - Enhanced with AI Agent

## Overview
ProductScraper is an intelligent web scraping tool that uses AI-powered element recognition to extract product data from any e-commerce website.

## Key Features Added with AI Agent Enhancement

### 1. **AI-Powered Element Recognition** 
- Function: `recognize_elements_with_agent()`
- Analyzes HTML structure and page content using AI
- Identifies product containers, titles, prices, SKUs, and links intelligently
- Falls back gracefully when AI is unavailable

### 2. **Intelligent Product Detection**
- 5 pattern-matching strategies:
  - Table Rows (TR)
  - Div Containers
  - List Items
  - Article Layout
  - Generic Elements
- Automatic scoring and selection of best pattern
- Less strict validation for difficult websites

### 3. **AI-Powered Data Validation & Enrichment**
- Function: `validate_products_with_ai()`
- **Duplicate Removal**: Eliminates duplicate products by title matching
- **Data Cleaning**: 
  - Price formatting and normalization
  - SKU uppercase conversion
  - Currency symbol removal
- **Confidence Scoring**: Each product gets a confidence score (0-1.0) based on:
  - Presence of price (-0.2 if missing)
  - Presence of SKU (-0.1 if missing)
  - Title length validation (-0.15 if too short)

### 4. **Multi-Level Extraction Strategy**
- Tries multiple extraction approaches for each field:
  - Primary: CSS selector from detected pattern
  - Secondary: Heading tag extraction (h1-h5)
  - Tertiary: Full text regex matching
- Regex patterns for currency extraction ($, £, €, ₹)
- Handles missing elements gracefully

### 5. **Production-Ready Features**
- Robust error handling with detailed logging
- Support for dynamic content (scrolling triggers)
- JavaScript rendering support via Selenium
- Automatic chrome driver management
- JSON output with timestamps

## Functions

### `get_driver()`
Initializes Chrome WebDriver with optimized options for scraping

### `detect_product_selectors(driver)`
Analyzes page structure and returns best CSS selectors for product elements

### `recognize_elements_with_agent(driver, page_content)`
**NEW**: Uses AI Agent to intelligently recognize product elements

### `extract_products(driver, selectors)`
Extracts product data using detected selectors and AI analysis

### `validate_products_with_ai(products, url)`
**NEW**: Validates and enriches extracted products with AI logic:
- Removes duplicates
- Cleans data formatting
- Adds confidence scores
- Normalizes fields

### `ProductScraperTool(url)`
Main entry point - orchestrates the entire scraping pipeline

## Usage

### Basic Usage
```python
from AMAVAGENT.ProductScraper import ProductScraperTool

url = "https://www.example-ecommerce.com/products"
result = ProductScraperTool(url)
print(result)
```

### Output Format
```json
{
  "url": "https://www.example-ecommerce.com/products",
  "products_found": 42,
  "products": [
    {
      "title": "Product Name",
      "price": "$99.99",
      "price_cleaned": "99.99",
      "sku": "SKU123",
      "url": "https://...",
      "confidence": 0.95
    }
  ],
  "timestamp": 1705600000.0
}
```

## AI Agent Integration

The tool now includes:
1. **Element Recognition**: AI analyzes page structure to suggest optimal CSS selectors
2. **Data Validation**: AI logic validates extracted data, removes duplicates, and adds quality scores
3. **Smart Extraction**: Multiple fallback strategies ensure products are found even on complex websites

### When AI Agent is Available
- Automatic element recognition
- Advanced duplicate detection
- Confidence-based filtering
- Data enrichment

### When AI Agent is Unavailable
- Falls back to pattern-based detection
- Manual CSS selector strategies
- Basic extraction still works perfectly

## Installation

```bash
pip install selenium webdriver-manager google-adk-agents
```

## Error Handling

- Chrome crashes: Automatically handled with experimental options
- Missing elements: Graceful fallback to alternative extraction methods
- Invalid pages: Returns 0 products instead of crashing
- Invalid JSON: Handled with UTF-8 encoding

## Performance

- **Timeout**: 10 seconds per page load
- **Scroll wait**: 2 seconds per scroll for dynamic content
- **Max products**: 200 per page (configurable)
- **Memory**: Efficient element disposal

## Configuration

Edit the main constants in ProductScraper.py:
- Container limit: `containers[:200]`
- Print limit: `extracted <= 10`
- Page load timeout: `WebDriverWait(driver, 10)`

## Future Enhancements

- [ ] Parallel scraping for multiple URLs
- [ ] Machine learning model training on website patterns
- [ ] Database storage integration
- [ ] Real-time monitoring and alerts
- [ ] Proxy rotation support
- [ ] Image extraction for products
