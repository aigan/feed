#!/bin/env python
# bin/browser_test_simple.py

import browser_cookie3
from playwright.sync_api import sync_playwright
import time
from urllib.parse import urlparse
from pprint import pprint

debug = False


def get_domain_cookies(url):
    """Get cookies for a specific domain using browser-cookie3"""
    domain = urlparse(url).netloc
    print(f"Extracting cookies for domain: {domain}")
    
    # Extract cookies from Chrome for this domain
    # This will get cookies from your default Chrome profile
    try:
        cookies = browser_cookie3.chrome(domain_name=domain)
        
        # Convert to Playwright format
        playwright_cookies = []
        for cookie in cookies:
            playwright_cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires,
                "secure": bool(cookie.secure),
                "httpOnly": cookie.has_nonstandard_attr('HttpOnly')
            })
        
        print(f"Found {len(playwright_cookies)} cookies")
        return playwright_cookies
    
    except Exception as e:
        print(f"Error extracting cookies: {e}")
        return []

def visit_site_with_cookies(url, cookies):
    """Visit a site using extracted cookies"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        context = browser.new_context()
        
        # Add the extracted cookies
        if cookies:
            #pprint(cookies);
            context.add_cookies(cookies)
        
        # Create a page and navigate
        print("New page");
        page = context.new_page()
        print("Goto url")
        page.goto(url)
        
        # Take a screenshot for verification
        time.sleep(1)
        page.screenshot(path="var/screenshot.png")
        print(f"Screenshot saved as screenshot.png")
        
        # Wait to see the browser
        #print("Waiting 5 seconds before closing...")
        #time.sleep(5)
        
        browser.close()

if __name__ == "__main__":
    target_url = "https://jonas.liljegren.org"
    print("Start");
    cookies = get_domain_cookies(target_url)
    print("Load")
    visit_site_with_cookies(target_url, cookies)
    print("Done")
