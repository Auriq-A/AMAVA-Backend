"""Run the API:  python -m amava_api  (uvicorn on HOST:PORT, default :51483)."""
from __future__ import annotations

import uvicorn

from .config import HOST, PORT


def main() -> None:
    # Same port the old server.py used, so the existing frontend works unchanged.
    uvicorn.run("amava_api.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
