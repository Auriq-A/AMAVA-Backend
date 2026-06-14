"""AMAVA agent layer: multi-tenant ADK tools + root agent.

The agent operates per signed-in user. The SaaS API opens an ADK session keyed
by the AMAVA user id; tools resolve that id and scope all data to the tenant.

    from amava_agent import root_agent          # ADK agent
    from amava_agent.services import run_supplier_scrape, build_user_spapi
"""
from .agent import root_agent

__all__ = ["root_agent"]
