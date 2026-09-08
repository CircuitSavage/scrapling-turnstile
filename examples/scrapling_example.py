"""Fetch a Turnstile-gated page with Scrapling, solve, and parse the result.

    pip install scrapling scrapling-turnstile
    scrapling install                 # one-time: pull the Camoufox browser
    export PEAK_API_KEY=pk_your_key   # Windows: set PEAK_API_KEY=pk_your_key
    python scrapling_example.py

StealthyFetcher is Camoufox under the hood, so it often clears a low-risk widget
on its own. ``turnstile_action`` returns that free token when it finds one and
only calls Peak when the widget stalls.
"""

import os

from scrapling.fetchers import StealthyFetcher

from scrapling_turnstile import turnstile_action

TARGET = "https://protected.example/login"

# Send Peak the same egress the fetch uses, so the token matches the session.
# Leave as None to solve proxyless.
PROXY = None  # e.g. "http://user:pass@host:port"


def main() -> None:
    page = StealthyFetcher.fetch(
        TARGET,
        headless=True,
        proxy=PROXY,
        # Wait until the widget is in the DOM before the action runs.
        wait_selector=".cf-turnstile",
        wait_selector_state="attached",
        # Solve (or reuse an already-earned token), inject, fire the callback.
        page_action=turnstile_action(
            api_key=os.environ["PEAK_API_KEY"],
            proxy=PROXY,
        ),
    )

    # `page` is a Scrapling Response/Adaptor — parse it straight away.
    print("status:", page.status)
    title = page.css_first("title::text")
    print("title:", title)


if __name__ == "__main__":
    main()
