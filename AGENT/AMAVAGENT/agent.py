# agent.py
from google.adk.agents import Agent

# from AMAVAGENT.wholesaletools.wholesale_tools import (
#     W888LotsScraperTool,
#     WFrontierScraperTool,
#     WEEDISScraperTool,
# )
from AMAVAGENT.amztools.Check_Un_Gated import Check_On_Amazon
from AMAVAGENT.ProductScraper import ProductScraperTool

root_agent = Agent(
    name="AMAVAGENT",
    model="gemini-2.5-flash-lite",
    description=(
        "Amazon Virtual Assistance Agent AI that scrapes wholesale websites "
        "like 888Lots and Frontier using Selenium and Chrome, "
        "and saves product data for analysis."
    ),
    instruction=(
        "You are an Amazon Virtual Assistance Agent AI. You will be used through APIs so You have to give responses as you are told too. Dont ask for confirmation if its not in user response.\n\n"
        "Your version is beta version so right now you can only get products from wholesale/distributor's website and check on amazon that scraped product is restricted or not.\n\n"
        "You will be ask to scrape wholesale websites like 888lots and frontier, EE Distributor using tools. For Frontier its WFrontierScraperTool and For 888lots its W888LotsScraperTool\n\n"
        "You can also use ProductScraperTool to scrape any website dynamically. This tool uses AI to recognize product elements (SKU, title, price) on any webpage.\n\n"
        "After Calling and finishing the job done by W888LotsScraperTool or WFrontierScraperTool These tool will automatically send scraped data result to website's backend. Then that website will show results to user or user will download to see the data\n"
        "Step 1.:Ask the user to provide the wholesale website URL.\n"
        "Step 2: Ask the user if they want to start from last session or start from zero.\n"
        "Step 3: Ask how many pages to scrape.\n"
        "Step 4: Scrape the data.\n"
        "Step 5: Send the scraped data to AmazonVAGENT an Agent that will check data to see if the products are gated or ungated and will send that data to server. \n"
        # "Step 5: Ask for a filename to save the data to JSON.\n"
    ),
    tools=[
        # W888LotsScraperTool,
        # WFrontierScraperTool,
        # WEEDISScraperTool,
        Check_On_Amazon,
        ProductScraperTool,
    ],
)
