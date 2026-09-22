"""Capture 6 portfolio screenshots of the live Streamlit app.

Usage:
    .venv/bin/python docs/capture_screenshots.py

Requires: playwright (installed in the venv). Chromium already downloaded via
`playwright install chromium`.

Writes:
    docs/screenshots/01-landing.png
    docs/screenshots/02-yield-dashboard.png
    docs/screenshots/03-root-cause-response.png
    docs/screenshots/04-agent-trace.png
    docs/screenshots/05-critical-suppliers.png
    docs/screenshots/06-bom-verifier.png

Also prints the LLM backend indicator so you can verify NVIDIA_API_KEY / ANTHROPIC_API_KEY is set on the Space.
"""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

URL = "https://nvidia-semiconductor-mcp.streamlit.app/"
OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1920, "height": 1200}

# Streamlit needs generous waits: initial JS bundle + LLM API calls
INITIAL_WAIT_S = 12
LLM_WAIT_S = 45


def _wait_streamlit_idle(page: Page, timeout_s: int = 60) -> None:
    """Wait until Streamlit's 'RUNNING' indicator disappears (script done)."""
    try:
        page.wait_for_selector('div[data-testid="stStatusWidget"]', state="visible", timeout=3000)
        page.wait_for_selector('div[data-testid="stStatusWidget"]', state="hidden", timeout=timeout_s * 1000)
    except Exception:
        page.wait_for_timeout(2000)


def _click_button_by_text(page: Page, contains: str) -> bool:
    """Click the first Streamlit button whose text contains `contains`. Returns True if found."""
    buttons = page.locator("button").all()
    for b in buttons:
        try:
            txt = b.inner_text(timeout=500).strip()
            if contains.lower() in txt.lower():
                b.click()
                return True
        except Exception:
            continue
    return False


def capture_all() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = ctx.new_page()

        print(f"[1/6] loading {URL} ...")
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(INITIAL_WAIT_S * 1000)

        # Read backend indicator from sidebar caption
        try:
            backend_text = page.locator('text=/LLM backend/').inner_text(timeout=5000)
            print(f"  BACKEND INDICATOR: {backend_text}")
        except Exception:
            print("  BACKEND INDICATOR: (not found in DOM — check manually)")

        # 1. Landing
        page.screenshot(path=str(OUT / "01-landing.png"), full_page=True)
        print(f"  wrote {OUT / '01-landing.png'}")

        # 2. Yield dashboard — change design dropdown to D-5023
        print("[2/6] setting design filter to D-5023 ...")
        # Streamlit selectbox: click to open, then click option
        try:
            selectbox = page.locator('div[data-baseweb="select"]').first
            selectbox.click()
            page.wait_for_timeout(500)
            page.get_by_text("D-5023", exact=True).first.click()
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"  selectbox interaction failed ({e}) — capturing default")
        page.screenshot(path=str(OUT / "02-yield-dashboard.png"), full_page=True)
        print(f"  wrote {OUT / '02-yield-dashboard.png'}")

        # 3. Root-cause response — click Q1
        print("[3/6] clicking Q1 (root cause query) ...")
        if _click_button_by_text(page, "Why did yield drop on lot W-2026-0142"):
            page.wait_for_timeout(2000)
            _wait_streamlit_idle(page, timeout_s=LLM_WAIT_S)
            page.wait_for_timeout(3000)
        else:
            print("  Q1 button not found")
        page.screenshot(path=str(OUT / "03-root-cause-response.png"), full_page=True)
        print(f"  wrote {OUT / '03-root-cause-response.png'}")

        # 4. Agent trace expanded
        print("[4/6] expanding agent trace ...")
        try:
            trace_expander = page.get_by_text("Agent trace").first
            trace_expander.click()
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  trace expander not found ({e})")
        page.screenshot(path=str(OUT / "04-agent-trace.png"), full_page=True)
        print(f"  wrote {OUT / '04-agent-trace.png'}")

        # 5. Critical suppliers — click Q8
        print("[5/6] clicking Q8 (critical suppliers) ...")
        if _click_button_by_text(page, "critical-risk list"):
            page.wait_for_timeout(2000)
            _wait_streamlit_idle(page, timeout_s=LLM_WAIT_S)
            page.wait_for_timeout(3000)
        else:
            print("  Q8 button not found")
        page.screenshot(path=str(OUT / "05-critical-suppliers.png"), full_page=True)
        print(f"  wrote {OUT / '05-critical-suppliers.png'}")

        # 6. BOM verifier — click Q3
        print("[6/6] clicking Q3 (BOM verifier) ...")
        if _click_button_by_text(page, "list all BOM parts"):
            page.wait_for_timeout(2000)
            _wait_streamlit_idle(page, timeout_s=LLM_WAIT_S)
            page.wait_for_timeout(3000)
        else:
            print("  Q3 button not found")
        try:
            page.get_by_text("Agent trace").last.click()
            page.wait_for_timeout(2000)
        except Exception:
            pass
        page.screenshot(path=str(OUT / "06-bom-verifier.png"), full_page=True)
        print(f"  wrote {OUT / '06-bom-verifier.png'}")

        browser.close()
    print("\ndone. 6 screenshots in docs/screenshots/")


if __name__ == "__main__":
    capture_all()
