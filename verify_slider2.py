from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Setting up localstorage...")
        page.goto("http://localhost:5173")
        page.evaluate("localStorage.setItem('sb_token', 'mock_token_123');")

        print("Navigating to mock server...")
        page.goto("http://localhost:5173", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print("Clicking a day...")
        # Since .react-calendar__tile wasn't found, let's use the actual selector or xpath
        try:
            page.locator("button.react-calendar__tile").first.click(timeout=3000)
        except Exception as e:
            print("Fallback to JS click...")
            # We will use evaluate to find any element with a class starting with react-calendar__tile
            page.evaluate("""
                const tiles = document.querySelectorAll('button[class*="react-calendar__tile"]');
                if (tiles.length > 0) {
                    tiles[0].click();
                } else {
                    console.log("No calendar tiles found");
                }
            """)
        page.wait_for_timeout(1000)

        # Take a snapshot to see where we are
        page.screenshot(path="slider_step1.png")

        print("Attempting to type a task...")
        try:
            page.locator("input[placeholder*='Add']").fill("Focus Session")
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
        except Exception as e:
            print("Could not fill task:", e)

        page.screenshot(path="slider_step2.png")

        print("Clicking Start Focus...")
        try:
            # wait for Start Focus button
            page.locator("button:has-text('Start Focus')").click(timeout=3000)
        except Exception as e:
            print("Could not click Start Focus normally:", e)
            try:
                page.evaluate("""
                    const btns = Array.from(document.querySelectorAll('button'));
                    const startBtn = btns.find(b => b.textContent.includes('Start Focus'));
                    if(startBtn) startBtn.click();
                """)
            except Exception as e2:
                print("Could not JS click Start Focus:", e2)

        # Wait a bit for the session to "start" (mock server takes a few seconds)
        page.wait_for_timeout(4000)

        # Capture screenshot of the active session
        print("Capturing active session screenshot...")
        page.screenshot(path="slider_active.png")
        print("Done. Screenshot saved to slider_active.png")

        browser.close()

if __name__ == "__main__":
    run()
