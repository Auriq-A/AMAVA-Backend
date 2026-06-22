"""CLI entrypoint:  python -m supplier_scraper.teach <start_url>

Launches the Teach Mode wizard against a supplier site, then prints where the
recipe and session were saved.
"""
from __future__ import annotations

import asyncio
import sys

from .wizard import TeachWizard


def _usage() -> None:
    print("Usage: python -m supplier_scraper.teach <start_url>")
    print("Example: python -m supplier_scraper.teach https://app.avasam.com")


async def _main(start_url: str) -> int:
    wizard = TeachWizard(start_url)
    recipe = await wizard.run()

    print("\n" + "=" * 60)
    print(f"Recipe learned for: {recipe.domain}")
    print("=" * 60)
    print(f"  login page     : {recipe.login_url or '(none)'}")
    if recipe.requires_login:
        print(f"  username field : {recipe.username_selector}")
        print(f"  password field : {recipe.password_selector}")
        print(f"  submit button  : {recipe.submit_selector}")
    print(f"  products page  : {recipe.products_url}")
    print(f"  min products   : {recipe.min_products}")
    print(f"  fields         : {', '.join(recipe.fields)}")
    print("-" * 60)
    saved = wizard.saved
    print(f"  recipe saved   : {saved.get('recipe_path')}")
    print(f"  session saved  : {saved.get('session_path')}")
    if saved.get("db_user_id"):
        print(f"  DB (encrypted) : user_id={saved['db_user_id']} (vault: {recipe.domain})")
    elif saved.get("db_error"):
        print(f"  DB             : {saved['db_error']}")
    print("=" * 60)
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        _usage()
        return 1
    return asyncio.run(_main(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
