"""Keep the Streamlit Community Cloud app awake.

Streamlit puts an app to sleep after ~12 hours without a visitor and shows a "get this app back up" page instead.
This opens the app in a headless browser, clicks the wake button if it is shown, and waits until the real
dashboard has rendered. It exits 1 if the app never comes up, so the workflow turns red and GitHub emails you.

    python -m src.keep_awake [--url URL]      # needs: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

log = logging.getLogger("keep_awake")

DEFAULT_URL = "https://texas-grid-ram.streamlit.app"
WAKE_BUTTON = "Yes, get this app back up!"   # the button on Streamlit's sleep page
APP_MARKER = "Texas Grid & Weather"          # st.title in dashboard/app.py; only present once the app has rendered
SLEEP_MARKER = "gone to sleep"               # "This app has gone to sleep due to inactivity"


def classify(texts: list[str]) -> str:
    """'awake' if the dashboard title is on the page (any frame), 'asleep' if the sleep page is, else 'loading'."""
    joined = "\n".join(texts)
    if APP_MARKER in joined:
        return "awake"
    if WAKE_BUTTON in joined or SLEEP_MARKER in joined:
        return "asleep"
    return "loading"


def page_texts(page) -> list[str]:
    """Visible text of the page and of every iframe (Streamlit renders the app inside an iframe)."""
    texts = []
    for frame in page.frames:
        try:
            texts.append(frame.inner_text("body", timeout=2_000))
        except Exception:  # a frame can be mid-navigation; just look again on the next poll
            pass
    return texts


def keep_awake(url: str = DEFAULT_URL, wake_timeout: int = 240, poll_seconds: float = 3.0) -> str:
    """Visit the app once. Returns 'awake' (was already up) or 'woken'. Raises RuntimeError if it never comes up."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            clicked = False
            deadline = time.monotonic() + wake_timeout
            while time.monotonic() < deadline:
                state = classify(page_texts(page))
                if state == "awake":
                    result = "woken" if clicked else "awake"
                    log.info("App is up (%s)", result)
                    return result
                if state == "asleep" and not clicked:
                    log.info("App is asleep, clicking the wake button")
                    page.get_by_role("button", name=WAKE_BUTTON).click(timeout=10_000)
                    clicked = True
                time.sleep(poll_seconds)
            raise RuntimeError(f"{url} did not show the dashboard within {wake_timeout}s")
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=int, default=240, help="seconds to wait for the dashboard to render")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        keep_awake(args.url, args.timeout)
    except Exception as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
