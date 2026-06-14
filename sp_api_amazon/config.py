"""Credentials and runtime configuration for the SP-API client.

Two small dataclasses:
  * Credentials - the secrets (LWA app + refresh token, optional AWS keys).
  * SPAPIConfig - everything the client needs at runtime: credentials, the
    chosen marketplace/region, sandbox flag, and tunables (timeouts, retries).

Both can be built explicitly or hydrated from environment variables, so the
agent layer can just do `AmazonSPAPI()` and have it read the project `.env`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .exceptions import SPAPIConfigError
from .marketplaces import Marketplace, Region, REGIONS, resolve_marketplace

# Best-effort .env loading. The project already uses python-dotenv via ADK; if
# it isn't installed we simply rely on the real environment.
try:  # pragma: no cover - environment dependent
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 - dotenv is optional
    pass


@dataclass
class Credentials:
    """LWA application credentials plus the seller's refresh token.

    AWS keys are optional and only used when SigV4 signing is explicitly
    enabled; modern SP-API does not require them.
    """

    lwa_client_id: str
    lwa_client_secret: str
    refresh_token: str
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    role_arn: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "SPAPI_") -> "Credentials":
        """Read credentials from environment variables.

        Expected (with default prefix ``SPAPI_``):
            SPAPI_LWA_CLIENT_ID, SPAPI_LWA_CLIENT_SECRET, SPAPI_REFRESH_TOKEN
        Optional (only for SigV4):
            SPAPI_AWS_ACCESS_KEY_ID, SPAPI_AWS_SECRET_ACCESS_KEY, SPAPI_ROLE_ARN
        """
        client_id = os.getenv(f"{prefix}LWA_CLIENT_ID")
        client_secret = os.getenv(f"{prefix}LWA_CLIENT_SECRET")
        refresh_token = os.getenv(f"{prefix}REFRESH_TOKEN")

        missing = [
            name
            for name, val in (
                (f"{prefix}LWA_CLIENT_ID", client_id),
                (f"{prefix}LWA_CLIENT_SECRET", client_secret),
                (f"{prefix}REFRESH_TOKEN", refresh_token),
            )
            if not val
        ]
        if missing:
            raise SPAPIConfigError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return cls(
            lwa_client_id=client_id,            # type: ignore[arg-type]
            lwa_client_secret=client_secret,    # type: ignore[arg-type]
            refresh_token=refresh_token,        # type: ignore[arg-type]
            aws_access_key_id=os.getenv(f"{prefix}AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv(f"{prefix}AWS_SECRET_ACCESS_KEY"),
            role_arn=os.getenv(f"{prefix}ROLE_ARN"),
        )

    @property
    def has_aws_keys(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)


@dataclass
class SPAPIConfig:
    """Everything the client needs to make a request."""

    credentials: Credentials
    marketplace: Marketplace
    sandbox: bool = False
    use_sigv4: bool = False
    # Selling-partner / merchant token. Required by a few APIs (e.g. Listings
    # Items) that key resources on the seller id rather than the marketplace.
    seller_id: str | None = None
    # HTTP / retry tunables.
    timeout: float = 30.0
    max_retries: int = 3
    backoff_base: float = 0.5      # seconds; exponential backoff base
    backoff_max: float = 30.0      # cap on a single backoff sleep
    user_agent: str = "AMAVA-SP-API/0.1 (Language=Python)"
    # Extra default headers, if ever needed.
    default_headers: dict[str, str] = field(default_factory=dict)

    @property
    def region(self) -> Region:
        return self.marketplace.region

    @property
    def endpoint(self) -> str:
        """The base host for this region, honoring the sandbox flag."""
        r = self.region
        return r.sandbox_endpoint if self.sandbox else r.endpoint

    @classmethod
    def resolve(
        cls,
        credentials: Credentials | None = None,
        *,
        marketplace: str | Marketplace = "US",
        region: str | Region | None = None,
        sandbox: bool = False,
        use_sigv4: bool = False,
        env_prefix: str = "SPAPI_",
        **tunables: object,
    ) -> "SPAPIConfig":
        """Build a config from a mix of explicit args and the environment.

        ``marketplace`` may be a short name ("US"), country code, raw ID, or a
        Marketplace instance. ``region`` is normally derived from the
        marketplace; pass it only to override.
        """
        if credentials is None:
            credentials = Credentials.from_env(env_prefix)

        mp = (
            marketplace
            if isinstance(marketplace, Marketplace)
            else resolve_marketplace(
                marketplace or os.getenv(f"{env_prefix}MARKETPLACE", "US")
            )
        )

        # Region override (rarely needed): rebuild the marketplace pointing at
        # the requested region while keeping its ID.
        if region is not None:
            reg = region if isinstance(region, Region) else REGIONS[str(region).lower()]
            mp = Marketplace(mp.name, mp.country_code, mp.marketplace_id, reg)

        sandbox = sandbox or os.getenv(f"{env_prefix}SANDBOX", "").lower() in (
            "1",
            "true",
            "yes",
        )

        return cls(
            credentials=credentials,
            marketplace=mp,
            sandbox=sandbox,
            use_sigv4=use_sigv4,
            seller_id=os.getenv(f"{env_prefix}SELLER_ID"),
            **tunables,  # type: ignore[arg-type]
        )
