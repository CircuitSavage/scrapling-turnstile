<a href="https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile">
  <img src="https://raw.githubusercontent.com/CircuitSavage/scrapling-turnstile/main/assets/peak-banner.png" alt="Peak — solve Cloudflare Turnstile and the 5s challenge in about a second" width="100%">
</a>

# scrapling-turnstile

Solve Cloudflare Turnstile inside a [Scrapling](https://github.com/D4Vinci/Scrapling) `StealthyFetcher` fetch. It reads the sitekey off the page, gets a token from [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile), writes it into `cf-turnstile-response`, and fires the widget callback — so the fetch clears the Turnstile/403 wall and you parse the page you actually wanted.

```python
from scrapling.fetchers import StealthyFetcher
from scrapling_turnstile import turnstile_action

page = StealthyFetcher.fetch(url, page_action=turnstile_action(api_key="pk_your_api_key"))
print(page.css_first("h1::text"))
```

## Why this exists

`StealthyFetcher` runs Camoufox, a fingerprint-patched Firefox. That fingerprint is real enough that plenty of low-risk Turnstile widgets pass on their own, and this package leans on that first: it checks whether `cf-turnstile-response` is already filled and, if it is, hands you that token for free.

The wall shows up when the widget scores the session as risky. Turnstile weighs the IP and the session history, not the checkbox. From a datacenter IP with no trusted past, a fetch gets held at the "Verifying..." spinner or looped through an invisible challenge that never resolves — and Scrapling hands you a 403 or the challenge HTML instead of the page. Waiting longer does nothing, because the token you need is minted by Cloudflare's risk engine, not by the interaction.

So when the native pass stalls, this reads the sitekey, sends it to Peak, and injects the token Cloudflare's `siteverify` will accept. Drop in an API key and the blocked fetch keeps moving.

## Install

```bash
pip install scrapling scrapling-turnstile
scrapling install   # one-time: pull the Camoufox browser Scrapling drives
```

The package itself has no runtime dependencies — it drives the Scrapling page you already have. `scrapling` is the fetcher you run it against.

## Quickstart

`turnstile_action()` returns a `page_action` you hand straight to `StealthyFetcher.fetch`. Scrapling calls it with the live page, the action solves and injects, and you get a parsed response back.

```python
import os
from scrapling.fetchers import StealthyFetcher
from scrapling_turnstile import turnstile_action

page = StealthyFetcher.fetch(
    "https://protected.example/login",
    headless=True,
    wait_selector=".cf-turnstile",       # let the widget render first
    wait_selector_state="attached",
    page_action=turnstile_action(
        api_key=os.environ["PEAK_API_KEY"],
    ),
)

print("status:", page.status)
print("title:", page.css_first("title::text"))
```

Set the key once and let it read from the environment:

```bash
export PEAK_API_KEY=pk_your_api_key   # Windows: set PEAK_API_KEY=pk_your_api_key
```

```python
page_action=turnstile_action()   # picks up PEAK_API_KEY
```

Prefer to drive the page yourself? Call the solver inside your own action:

```python
from scrapling_turnstile import solve_turnstile

def action(page):
    page.wait_for_timeout(2500)          # let the widget settle
    solve_turnstile(page, proxy="http://user:pass@host:port")
    page.click("button[type=submit]")
    return page

page = StealthyFetcher.fetch(url, page_action=action)
```

A full runnable script is in [`examples/scrapling_example.py`](./examples/scrapling_example.py).

### Async

`StealthyFetcher.async_fetch` gets an async page, so use the async twins:

```python
from scrapling.fetchers import StealthyFetcher
from scrapling_turnstile import async_turnstile_action

page = await StealthyFetcher.async_fetch(
    url,
    page_action=async_turnstile_action(api_key="pk_your_api_key"),
)
```

## Native pass vs. an API solve

Scrapling's stealth and Peak cover different failure modes. Use them together.

- **Let Scrapling try first.** `StealthyFetcher` on a clean fingerprint clears most non-interactive widgets with no solve at all. Give it a real locale and — for anything that matters — a residential or ISP `proxy`. `turnstile_action` returns that free token when it finds one, so you pay nothing on the pages that were never going to block you.
- **Solve through Peak when it stalls.** Datacenter egress, a high-risk sitekey, or an aggressive site will hold the widget open no matter how good the browser is. That is the case Peak handles: it returns a token minted against the sitekey, independent of your fetch's browser session.
- **Match the egress.** If you pass a `proxy` to Peak, use the same IP the fetch goes out on. A token solved from one network and replayed from another is more likely to be rejected server-side.

## What it does not do

- **Not the full-page interstitial.** The Cloudflare "Just a moment" page that gates a whole domain and sets `cf_clearance` is a different challenge from an embedded Turnstile widget. This package handles the widget — the one that renders a `cf-turnstile` element and a `cf-turnstile-response` field. For the interstitial, Peak has a separate `cloudflare5stask`; see the [docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile).
- **Not reCAPTCHA or hCaptcha.** Turnstile only.
- **No magic on a banned IP.** If the target already blocked your IP range, get a better egress first. A valid token on a burned network still gets refused.

## API

### `turnstile_action(api_key=None, proxy=None, sitekey=None, timeout=180.0, use_existing=True)`

Build a `page_action` for `StealthyFetcher.fetch(page_action=...)`. Solves, injects, and returns the page — the contract Scrapling expects. Keyword arguments match `solve_turnstile`.

### `solve_turnstile(page, api_key=None, proxy=None, sitekey=None, timeout=180.0, use_existing=True)`

Get a valid Turnstile token onto a `page` and inject it. Returns the token. Call it from inside your own `page_action` when you want to do more than solve.

- `page` — the sync Playwright page handed to your action by `StealthyFetcher.fetch`, on a Turnstile-gated URL.
- `api_key` — Peak key (`pk_...`). Falls back to `PEAK_API_KEY`.
- `proxy` — optional proxy handed to Peak, e.g. `http://user:pass@host:port`. Use the same egress as the fetch.
- `sitekey` — skip the DOM read and use this sitekey.
- `timeout` — seconds to wait on Peak.
- `use_existing` — if `True` (default), return a token Scrapling already earned instead of paying for a solve.

### `read_sitekey(page)`

Return the Turnstile sitekey rendered on the page (from `.cf-turnstile[data-sitekey]`, any `[data-sitekey]`, or the `challenges.cloudflare.com` iframe `src`), or `None`.

### `existing_token(page)`

Return the token in `cf-turnstile-response` if Scrapling already passed the widget, else `None`.

### `inject_token(page, token)`

Write `token` into the response field(s) and fire the widget's `data-callback`. Returns `True` if a callback was found and called.

### `request_token(sitekey, url, api_key=None, proxy=None, timeout=180.0)`

The raw, blocking Peak call, in case you want the token without a page. Returns the token string or raises `PeakError`.

**Async twins:** `async_turnstile_action`, `async_solve_turnstile`, `async_read_sitekey`, `async_existing_token`, `async_inject_token` — same signatures, for `StealthyFetcher.async_fetch`.

## How it works

1. If `use_existing`, read `cf-turnstile-response`; a filled field means Scrapling already passed, so return that token and skip the solve.
2. Read the sitekey from the widget, or scrape it from the Cloudflare iframe `src` when the widget rendered implicitly.
3. Call Peak `POST https://api.peak.fo/solve` with `task_type: "turnstiletask"`, the `sitekey`, `url: page.url`, and your optional `proxy` — over `X-API-Key`. Peak returns `{"success": true, "data": {"token": "..."}}`.
4. Inject the token into every `cf-turnstile-response` field (creating a hidden input if the widget hasn't rendered one) and invoke the widget's `data-callback`, so the host page's success handler runs.

The sync path calls Peak inline, which is fine inside a synchronous `fetch` action. The async path runs the blocking call in a worker thread so the browser's event loop keeps ticking.

## Powered by Peak

This uses [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile), a Cloudflare specialist that returns a Turnstile token in about a second.

- **$0.90 per 1,000** successful Turnstile solves, down to **$0.35 at volume**.
- **Pay only for successes** — a failed solve is not billed.
- **About 1,000 free solves** to start, no card.

→ [Get a free API key](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile) · [Turnstile docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=scrapling-turnstile)

## Other Peak wrappers

Same solve, wired into other stacks:

- [camoufox-turnstile](https://github.com/CircuitSavage/camoufox-turnstile) — Turnstile in Camoufox (the browser under Scrapling's `StealthyFetcher`).
- [playwright-turnstile](https://github.com/CircuitSavage/playwright-turnstile) — token injection for Playwright.
- [selenium-turnstile](https://github.com/CircuitSavage/selenium-turnstile) — a valid token in Selenium, no physical click.
- [scrapy-turnstile](https://github.com/CircuitSavage/scrapy-turnstile) — Scrapy middleware that keeps blocked spiders running.
- [puppeteer-extra-plugin-turnstile](https://github.com/CircuitSavage/puppeteer-extra-plugin-turnstile) — a `puppeteer-extra` plugin.
- [turnstile-curl](https://github.com/CircuitSavage/turnstile-curl) — solve from `curl_cffi`, no browser.
- [cloudscraper-turnstile](https://github.com/CircuitSavage/cloudscraper-turnstile) — a `cloudscraper` drop-in.
- [crawl4ai-turnstile](https://github.com/CircuitSavage/crawl4ai-turnstile) — Turnstile solving for Crawl4AI.

More on the list: [awesome-turnstile-solvers](https://github.com/CircuitSavage/awesome-turnstile-solvers).

## Legitimate use

Built for automation, QA, and scraping public data. Respect each site's Terms of Service and `robots.txt`, and don't point it at credential-stuffing or other abuse. How you use it is on you.

## License

MIT — see [LICENSE](./LICENSE).
