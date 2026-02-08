#!/bin/env python
from playwright.sync_api import sync_playwright

from config import CHROME_PROFILE, CHROME_USER_DIR


def get_browser_context(headless=False):
    """Create a browser context using the configured Chrome profile"""
    playwright = sync_playwright().start()
    browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir=CHROME_USER_DIR,
        headless=headless,
        args=["--profile-directory=" + CHROME_PROFILE]
    )

    return browser_context, playwright

def close_browser(context, playwright):
    """Close browser resources"""
    if context:
        context.close()
    if playwright:
        playwright.stop()

browser_context, playwright = get_browser_context(headless=True)
page = browser_context.new_page()

# Navigate to history page
print("Navigating to YouTube history...")
page.goto("https://www.youtube.com/feed/history")

# Check if we're logged in
if page.locator("text=Sign in").count() > 0:
    print("Error: Not logged in to YouTube")
    exit(1)

# Wait for content to load
print("Waiting for content...")
page.wait_for_selector("ytd-video-renderer", timeout=30000)

# Scroll to load more videos
video_count = 0
prev_count = -1

print("Loading videos by scrolling...")
while video_count < max_videos and video_count != prev_count:
    prev_count = video_count
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(2000)  # Wait for content to load
    video_count = page.locator("ytd-video-renderer").count()
    print(f"Loaded {video_count} videos")
