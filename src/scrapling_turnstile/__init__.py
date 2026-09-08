"""scrapling-turnstile — solve Cloudflare Turnstile in Scrapling via Peak.

Read the sitekey off a StealthyFetcher page, solve through the Peak API, inject
the token, keep fetching. Sync helpers for ``StealthyFetcher.fetch`` and async
twins for ``StealthyFetcher.async_fetch``.
"""

from .peak import PeakError, request_token
from .solver import (
    async_existing_token,
    async_inject_token,
    async_read_sitekey,
    async_solve_turnstile,
    async_turnstile_action,
    existing_token,
    inject_token,
    read_sitekey,
    solve_turnstile,
    turnstile_action,
)

__all__ = [
    # sync
    "solve_turnstile",
    "turnstile_action",
    "read_sitekey",
    "existing_token",
    "inject_token",
    # async
    "async_solve_turnstile",
    "async_turnstile_action",
    "async_read_sitekey",
    "async_existing_token",
    "async_inject_token",
    # peak client
    "request_token",
    "PeakError",
]

__version__ = "0.1.0"
