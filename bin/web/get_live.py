#!/bin/env python

import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# Get environment variables (from direnv)
chrome_user_dir = os.environ.get('CHROME_USER_DIR', '~/.config/google-chrome')
chrome_profile = os.environ.get('CHROME_PROFILE', 'Profile 1')

# Ensure the user directory is expanded
chrome_user_dir = str(Path(chrome_user_dir).expanduser())

print(f"Using Chrome profile: {chrome_profile}")
print(f"Chrome user directory: {chrome_user_dir}")

def dump_html(page, filename=None):
    """Dump the current page HTML for debugging"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_dump_{timestamp}.html"

    html_content = page.content()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML dumped to {filename}")

page_url = "https://jonas.liljegren.org"

# Start Playwright
with sync_playwright() as p:
    try:
        # Launch browser with visible UI (not headless)
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=chrome_user_dir,
            headless=False,  # Show the browser window
            slow_mo=100,     # Slow down actions for visibility
            args=["--profile-directory=" + chrome_profile]
        )

        # Create a new page
        page = browser_context.new_page()

        # Navigate to a simple website
        print("Navigating to page...")
        page.goto(page_url)

        # Wait to ensure page is loaded
        page.wait_for_load_state("networkidle")

        # Take a screenshot
        page.screenshot(path="var/example_screenshot.png")
        print("Screenshot saved as example_screenshot.png")

        # Extract some basic information
        title = page.title()
        h = page.locator("h1, h2").first
        heading = h.inner_text() if h.count() else "(no heading)"

        print(f"Page title: {title}")
        print(f"Main heading: {heading}")

        # Dump HTML for debugging
        dump_html(page, "var/example_dump.html")

        # Wait a bit to see the browser
        print("Waiting 5 seconds before closing...")
        time.sleep(5)

    except Exception as e:
        print(f"Error: {str(e)}")
        # Try to dump HTML if there's an error
        try:
            dump_html(page, "var/error_dump.html")
        except:
            print("Could not dump HTML after error")

    finally:
        # Close the browser
        if 'browser_context' in locals():
            browser_context.close()
        print("Browser closed")

print("Script completed")
