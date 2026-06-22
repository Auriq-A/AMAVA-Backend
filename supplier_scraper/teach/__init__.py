"""Teach Mode — interactive, record-once scraping setup.

Instead of fighting headless detection and guessing selectors, the user drives
a visible browser once while the agent watches and asks confirmation questions
through an in-page overlay. What it learns (login form, products page, target
count, fields) is saved as a reusable recipe + session, so future runs replay
automatically.

    from supplier_scraper.teach import TeachWizard, RecipeStore, SupplierRecipe

    recipe = await TeachWizard("https://app.avasam.com").run()

Or from the command line:

    python -m supplier_scraper.teach https://app.avasam.com
"""
from __future__ import annotations

from .recipe import (
    RecipeStore,
    SupplierRecipe,
    domain_of,
    load_from_vault,
    save_to_vault,
)
from .replay import replay
from .wizard import TeachWizard

__all__ = [
    "TeachWizard",
    "replay",
    "RecipeStore",
    "SupplierRecipe",
    "domain_of",
    "save_to_vault",
    "load_from_vault",
]
