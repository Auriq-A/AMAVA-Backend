# tools/wholesale_tools.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from typing import Optional
import os
from AMAVAGENT.wholesaletools.T8lots_Scraper import RealScraper
# Setup Selenium globally (or use a singleton if reused often)
def get_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.use_chromium = True
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.add_argument(r"--user-data-dir=C:\test-chrome")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("start-maximized")
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-site-isolation-trials')
    chrome_options.add_argument("--load-extension=D:/AMAVA/888lots")
    chrome_options.add_argument("--load-extension=D:/AMAVA/Frontier")
    chrome_options.add_argument("--load-extension=D:/AMAVA/EEDIS")
    # chrome_options.add_argument("--headless")  # Start maximized


    service = ChromeService(r"C:\Users\Black\Downloads\chromedriver-win64 (1)\chromedriver-win64\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def W888LotsScraperTool(category_url: str, pages: int = 3, startFromZero: bool = True) -> str:
    """
    Scrapes product data from the given 888Lots category URL up to a number of pages.
    """
    driver = get_driver()
        
    driver.get(f"{category_url}&pagelimit={pages}&startbutton={'yes' if startFromZero else 'no'}")

    # Run scraper (injected JS etc.)
    RealScraper(driver=driver, current_url=category_url, pages=pages, startFromZero=startFromZero)

    return f"Scraping finished for {category_url} (up to {pages} pages)"

def WFrontierScraperTool(category_url: str, pages: int = 3, startFromZero: bool = True):
    """
    Placeholder tool to scrape from Frontier (future implementation)
    """
    try: 
        driver = get_driver()
    except:
        return None
    
    driver.get(f"{category_url}&pagelimit={pages}&startbutton={'yes' if startFromZero else 'no'}")
    RealScraper(driver=driver, current_url=category_url, pages=pages, startFromZero=startFromZero)
    return "Frontier scraper have been started."

def WEEDISScraperTool(category_url: str, pages: int = 3, startFromZero: bool = True):
    """
    Placeholder tool to scrape from Frontier (future implementation)
    """
    try: 
        driver = get_driver()
    except:
        return None
    
    driver.get(f"{category_url}&pagelimit={pages}&startbutton={'yes' if startFromZero else 'no'}")
    RealScraper(driver=driver, current_url=category_url, pages=pages, startFromZero=startFromZero)
    return "EE scraper have been started."
