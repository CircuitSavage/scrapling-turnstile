"""Turnstile helpers for a Scrapling ``StealthyFetcher`` page.

``StealthyFetcher`` runs Camoufox (a fingerprint-patched Firefox) and hands your
``page_action`` a Playwright page. The flow here is DOM-first: read the sitekey
off the widget, get a token from Peak, write it into ``cf-turnstile-response``,
and fire the widget callback. No clicking, no waiting on a spinner that will
never resolve from a datacenter IP.

``StealthyFetcher.fetch`` is synchronous and its ``page_action`` gets a *sync*
Playwright page, so the primary helpers here are sync. Async twins are provided
for ``StealthyFetcher.async_fetch``.
"""

from __future__ import annotations

import asyncio

from .peak import PeakError, request_token

# Where the sitekey tends to live once Turnstile has rendered.
_SITEKEY_SELECTORS = (
    ".cf-turnstile[data-sitekey]",
    "[data-sitekey]",
    "iframe[src*='challenges.cloudflare.com']",
)

# Pull the sitekey in-page for the cases an element attribute won't cover:
# implicit render, an iframe-only widget, or a turnstile.render() config.
_READ_SITEKEY_JS = r"""() => {
  const el = document.querySelector('[data-sitekey]');
  if (el) return el.getAttribute('data-sitekey');
  const frame = document.querySelector("iframe[src*='challenges.cloudflare.com']");
  if (frame) {
    const m = (frame.getAttribute('src') || '').match(/[?&]sitekey=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
  }
  return null;
}"""

# If Camoufox already passed Turnstile on its own, the response field is filled.
# Read it so we can skip a paid solve entirely.
_READ_EXISTING_TOKEN_JS = r"""() => {
  const f = document.querySelector('[name="cf-turnstile-response"]');
  const v = f && f.value ? f.value.trim() : '';
  return v.length > 20 ? v : null;
}"""

# Write the token into every response field (making a hidden input if the widget
# hasn't rendered one), then call the widget's data-callback so the host page's
# own success handler runs.
_INJECT_TOKEN_JS = r"""(token) => {
  const name = 'cf-turnstile-response';
  let fields = Array.from(document.querySelectorAll(`[name="${name}"]`));
  if (fields.length === 0) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    (document.querySelector('form') || document.body).appendChild(input);
    fields = [input];
  }
  for (const f of fields) {
    f.value = token;
    f.dispatchEvent(new Event('input', { bubbles: true }));
    f.dispatchEvent(new Event('change', { bubbles: true }));
  }

  let callbackFired = false;
  const widget = document.querySelector('.cf-turnstile[data-callback], [data-callback]');
  if (widget) {
    const cb = widget.getAttribute('data-callback');
    if (cb && typeof window[cb] === 'function') {
      try { window[cb](token); callbackFired = true; } catch (e) {}
    }
  }
  return callbackFired;
}"""


# --------------------------------------------------------------------------- #
# Sync helpers — for StealthyFetcher.fetch(page_action=...)
# --------------------------------------------------------------------------- #


def read_sitekey(page):
    """Return the Turnstile sitekey rendered on ``page``, or None."""
    for selector in _SITEKEY_SELECTORS:
        element = page.query_selector(selector)
        if element is None:
            continue
        try:
            sitekey = element.get_attribute("data-sitekey")
        except Exception:
            sitekey = None
        if sitekey:
            return sitekey
    return page.evaluate(_READ_SITEKEY_JS)


def existing_token(page):
    """Return a token Camoufox already earned on its own, if the field is set.

    Scrapling's stealth is good enough that many low-risk widgets clear without
    help. Check here first and you avoid paying for a solve you don't need.
    """
    try:
        return page.evaluate(_READ_EXISTING_TOKEN_JS)
    except Exception:
        return None


def inject_token(page, token: str) -> bool:
    """Write ``token`` into the response field(s) and fire the widget callback.

    Returns True if a ``data-callback`` was found and invoked.
    """
    return bool(page.evaluate(_INJECT_TOKEN_JS, token))


def solve_turnstile(
    page,
    api_key: str | None = None,
    proxy: str | None = None,
    sitekey: str | None = None,
    timeout: float = 180.0,
    use_existing: bool = True,
) -> str:
    """Get a valid Turnstile token onto a Scrapling ``page`` and inject it.

    Order of play: if Camoufox already filled ``cf-turnstile-response`` and
    ``use_existing`` is set, return that token untouched. Otherwise read the
    sitekey, ask Peak for a token, inject it, and fire the widget callback so
    your submit or navigation goes through.

    Args:
        page: The sync Playwright ``Page`` handed to your ``page_action`` by
            ``StealthyFetcher.fetch``, sitting on a Turnstile-gated URL.
        api_key: Peak key (``pk_...``). Falls back to ``PEAK_API_KEY``.
        proxy: Proxy to hand Peak, e.g. ``http://user:pass@host:port``. Use the
            same egress the fetch uses so the token matches the session.
        sitekey: Skip the DOM read and use this sitekey.
        timeout: Seconds to wait on Peak.
        use_existing: Return a token Camoufox already earned instead of solving.

    Returns:
        The Turnstile token (also injected into the page).

    Raises:
        PeakError: no sitekey on the page, or Peak could not solve it.
    """
    if use_existing:
        already = existing_token(page)
        if already:
            return already

    if sitekey is None:
        sitekey = read_sitekey(page)
    if not sitekey:
        raise PeakError(
            "No Turnstile sitekey on the page. Has the widget rendered yet? "
            "Pass a wait_selector to StealthyFetcher, or sitekey=... if you "
            "already know it."
        )

    token = request_token(
        sitekey,
        page.url,
        api_key=api_key,
        proxy=proxy,
        timeout=timeout,
    )
    inject_token(page, token)
    return token


def turnstile_action(
    api_key: str | None = None,
    proxy: str | None = None,
    sitekey: str | None = None,
    timeout: float = 180.0,
    use_existing: bool = True,
):
    """Build a ``page_action`` for ``StealthyFetcher.fetch(page_action=...)``.

    Scrapling calls the action with the page and expects the page back. This
    wraps :func:`solve_turnstile` in that contract, so a whole protected fetch
    is one line::

        page = StealthyFetcher.fetch(url, page_action=turnstile_action())

    The keyword arguments match :func:`solve_turnstile`.
    """

    def _action(page):
        solve_turnstile(
            page,
            api_key=api_key,
            proxy=proxy,
            sitekey=sitekey,
            timeout=timeout,
            use_existing=use_existing,
        )
        return page

    return _action


# --------------------------------------------------------------------------- #
# Async helpers — for StealthyFetcher.async_fetch(page_action=...)
# --------------------------------------------------------------------------- #


async def async_read_sitekey(page):
    """Async twin of :func:`read_sitekey` for ``async_fetch`` pages."""
    for selector in _SITEKEY_SELECTORS:
        element = await page.query_selector(selector)
        if element is None:
            continue
        try:
            sitekey = await element.get_attribute("data-sitekey")
        except Exception:
            sitekey = None
        if sitekey:
            return sitekey
    return await page.evaluate(_READ_SITEKEY_JS)


async def async_existing_token(page):
    """Async twin of :func:`existing_token`."""
    try:
        return await page.evaluate(_READ_EXISTING_TOKEN_JS)
    except Exception:
        return None


async def async_inject_token(page, token: str) -> bool:
    """Async twin of :func:`inject_token`."""
    return bool(await page.evaluate(_INJECT_TOKEN_JS, token))


async def async_solve_turnstile(
    page,
    api_key: str | None = None,
    proxy: str | None = None,
    sitekey: str | None = None,
    timeout: float = 180.0,
    use_existing: bool = True,
) -> str:
    """Async twin of :func:`solve_turnstile` for ``StealthyFetcher.async_fetch``.

    The blocking Peak call runs in a worker thread so the browser's event loop
    keeps ticking.
    """
    if use_existing:
        already = await async_existing_token(page)
        if already:
            return already

    if sitekey is None:
        sitekey = await async_read_sitekey(page)
    if not sitekey:
        raise PeakError(
            "No Turnstile sitekey on the page. Has the widget rendered yet? "
            "Pass a wait_selector to StealthyFetcher, or sitekey=... if you "
            "already know it."
        )

    token = await asyncio.to_thread(
        request_token,
        sitekey,
        page.url,
        api_key=api_key,
        proxy=proxy,
        timeout=timeout,
    )
    await async_inject_token(page, token)
    return token


def async_turnstile_action(
    api_key: str | None = None,
    proxy: str | None = None,
    sitekey: str | None = None,
    timeout: float = 180.0,
    use_existing: bool = True,
):
    """Build an async ``page_action`` for ``StealthyFetcher.async_fetch``."""

    async def _action(page):
        await async_solve_turnstile(
            page,
            api_key=api_key,
            proxy=proxy,
            sitekey=sitekey,
            timeout=timeout,
            use_existing=use_existing,
        )
        return page

    return _action
