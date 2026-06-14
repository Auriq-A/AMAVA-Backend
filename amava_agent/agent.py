"""AMAVAGENT root agent (multi-tenant).

Wires the per-user tools into an ADK agent. Each request runs inside an ADK
session whose user_id identifies the tenant; the tools scope all data to that
user automatically.
"""
from __future__ import annotations

from google.adk.agents import Agent

from .tools import list_recent_products, scrape_supplier

root_agent = Agent(
    name="AMAVAGENT",
    model="gemini-2.5-flash-lite",
    description=(
        "Amazon Virtual Assistant agent. Scrapes wholesaler/supplier sites and "
        "manages the signed-in user's product data."
    ),
    instruction=(
        "You are AMAVAGENT, an Amazon virtual assistant operating on behalf of "
        "the currently signed-in user. You are used through an API, so respond "
        "concisely and do not ask for confirmation unless the user asked you to.\n\n"
        "Capabilities right now:\n"
        "- scrape_supplier: scrape a registered wholesaler/supplier (e.g. "
        "'888lots', 'avasam') for the user and save the products. Ask which "
        "supplier and how many pages if not given. Pass enrich=true only if "
        "the user wants full product details (description, images, specs, "
        "rating, stock) - it visits each product's page and is slower/costs "
        "more, so leave it off for a quick listing scrape.\n"
        "- list_recent_products: show the user's recently scraped products.\n\n"
        "All data is private to the signed-in user. If a tool reports no "
        "authenticated user, tell the user they must sign in."
    ),
    tools=[scrape_supplier, list_recent_products],
)
