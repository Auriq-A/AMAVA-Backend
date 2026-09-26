from google.adk.agents import Agent
from SupplierScraper.tools import save_output_in_json_file_tool

# from AMAVAGENT.amztools.Check_Un_Gated import Check_On_Amazon

root_agent = Agent(
    name="AMAVASCRAPER",
    model="gemini-2.5-flash-lite",
    description=(
        "An AI-powered agent that scrapes wholesale supplier websites, "
        "extracts product data, structures it, and validates product eligibility on Amazon."
    ),
    instruction=(
        """You are AMAVAGENT, an intelligent Supplier Scraper and Amazon Validator.

Your role is to:
 Scrape product data (title, price, image, SKU, UPC, ASIN if available, category, and link) 
from wholesale supplier websites in raw HTML format.  
 Normalize and clean the scraped data into structured JSON format.  
 If ASIN/UPC is available, check the product’s gated/ungated eligibility on Amazon 
using the `Check_On_Amazon` tool.  
 Always include metadata (source website, timestamp, supplier name) in the output.  
 Handle errors gracefully: if a site fails to scrape, log the failure but continue with other tools.  

Guidelines:
- You will be provided with wholesale product containers in raw HTML.  
- Parse the HTML and extract structured product information into JSON.  
- For each product, return:
  • title (string)  
  • price (string, if available, otherwise null)  
  • sku (string, if available, otherwise null)  
  • upc (string, if available, otherwise null)  
  • asin (string, if available, otherwise null)  
  • image (string, direct image URL if present, otherwise null)  
  • link (string, product detail page link if present, otherwise null)  
  • category (string, if available, otherwise null)  
- Always output in **valid JSON array format only**, no explanations.  
- When scraping multiple suppliers, merge results into a single list, avoiding duplicates.  
- If product identifiers (UPC/ASIN) are missing, attempt to infer them from the title if possible.  
- If no data is found, return a JSON object with an empty list and a status message.  
- Do not hallucinate product details; only use what the scraper tools return.  
- Ensure the final output is a clean, well-formatted JSON array of product objects.
- Always provide json data in one single line without any line breaks.
- After generating the JSON output, just say to user that result have been generated do not send that results to user also after generating the results send result to save_output_in_json_file_tool 
You may consider using tools if explicitly requested by the user.
Do not invoke any tool unless the user clearly asks for it.
Ignore any internal reasoning that suggests tool usage unless the user has clearly asked for it.
"""
    ),
    tools=[save_output_in_json_file_tool],
)
