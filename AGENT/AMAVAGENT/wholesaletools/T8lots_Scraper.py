from google.adk.agents import Agent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import threading

try:
    from webdriver_manager.chrome import ChromeDriverManager

    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

chrome_options = webdriver.ChromeOptions()
chrome_options.use_chromium = True

if USE_WEBDRIVER_MANAGER:
    # Use webdriver-manager to automatically download the correct ChromeDriver
    service = webdriver.ChromeService(ChromeDriverManager().install())
else:
    # Fallback to manual path
    service = webdriver.ChromeService(
        r"C:\Users\Black\Downloads\chromedriver-win64 (1)\chromedriver-win64\chromedriver.exe"
    )

chrome_options.add_argument(
    "--profile-directory=Default"
)  # Change this to your actual profile name
chrome_options.add_argument("--load-extension=D:/AMAVA/888lots")
chrome_options.add_argument("--load-extension=D:/AMAVA/EEDIS")
chrome_options.add_argument("--load-extension=D:/AMAVA/Frontier")
# chrome_options.add_argument('--disable-extensions')
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_argument(r"--user-data-dir=C:\test-chrome")
chrome_options.add_argument(
    "--disable-blink-features=AutomationControlled"
)  # Disable automation detection
# chrome_options.add_argument("--headless")  # Start maximized
driver = webdriver.Chrome(service=service, options=chrome_options)


def url_listener(check_interval=2):
    """
    Monitors URL changes and triggers the scraper only once per matching URL.
    """
    last_url = None

    while True:
        try:
            current_url = driver.current_url

            if current_url.startswith("https://888lots.com/items"):
                if last_url != current_url:
                    print(f"[Listener] New matching URL: {current_url}")
                    last_url = current_url
                    RealScraper(current_url, pages=5)
            else:
                last_url = None  # Reset if user navigates elsewhere
        except Exception as e:
            print(f"[Listener Error] {e}")

        time.sleep(check_interval)


def W888LotsLogin(Email: str, Password: str) -> None:
    driver.get("https://888lots.com/login/login")
    time.sleep(5)  # Wait for the page to load completely
    # Check if the page is loaded correctly
    if "Login" not in driver.title:
        print("Failed to load the login page.")
        time.sleep(5)

    jscode = f"""
    document.querySelector("#input-email")?.value="{Email}"
    document.querySelector("#input-password")?.value="{Password}"
    document.querySelector("#sub-content > div > div > div > form > div > div.bottom-form > input")?.click();
    """
    # Execute JavaScript to fill in the login form and submit
    try:
        driver.execute_script(jscode)
    except Exception as e:
        print(f"Error executing JavaScript: {e}")

    time.sleep(10)  # Wait for the login to complete
    RealScraper("https://888lots.com/items?category=personal-care-health-and-beauty", 5)


def RealScraper(
    driver, current_url: str, pages: int = 5, startFromZero: bool = True
) -> list:
    print(f"[Scraper] Launching for: {current_url}")

    # Step 1: Load base category URL (no extra params)
    # driver.get(current_url)
    # Wait until product cards load
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.item-body"))
    )

    # Step 2: Simulate page limit setting inside the page (if applicable)
    driver.execute_script(
        f"""
        try {{
            const page_limit = {pages};
            localStorage.setItem('scraper_pagelimit', page_limit); // Optional for reuse in script.js
            localStorage.setItem('startbutton', '{"yes" if startFromZero else "no" }'); // Optional for reuse in script.js
        }} catch (e) {{
            console.error("Page limit set failed", e);
        }}
    """
    )

    print("[Scraper] Injected scraper script.")

    # Step 4: Wait until JS finishes (up to you to design exit signal in script.js)
    time.sleep(15)  # Or use a loop to wait for window.__scrapeDone or a flag

    return [
        {
            "status": "In Progress",
            "message": "Scraping in progress... and will be send to the website",
        }
    ]


if __name__ == "__main__":
    # Optional: login
    # W888LotsLogin("info@sayaholdingllc.com", "amazonfba$")
    driver.get(
        "https://888lots.com/items?category=personal-care-health-and-beauty&pagelimit=3&startbutton=yes"
    )
    # Start listener in background
    listener_thread = threading.Thread(target=url_listener, daemon=True)
    listener_thread.start()

    print("Listener started. You can now navigate freely in the browser...")

    # Keep main thread alive
    while True:
        time.sleep(60)
