from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Route mocks to prevent timeouts
        page.route("**/api/auth/me", lambda route: route.fulfill(
            status=200,
            json={
                "id": 1,
                "email": "test@example.com",
                "username": "tester",
                "wallet": {
                    "balance": 3000,
                    "total_deposited": 5000,
                    "charity_ratio": 40
                }
            }
        ))

        page.route("**/api/business/me/tasks/status", lambda route: route.fulfill(
            status=200,
            json={"has_active_tasks": False, "total_tasks_today": 2, "completed_tasks_today": 0}
        ))

        print("Navigating to mock server...")
        # Localstorage trick to bypass auth
        page.goto("http://localhost:5173")
        page.evaluate("localStorage.setItem('sb_token', 'mock_token_123');")
        page.goto("http://localhost:5173", wait_until="domcontentloaded")

        print("Waiting for session store to be available or mocking the transition...")
        page.wait_for_timeout(2000)

        # Force state to active
        print("Evaluating state change to active...")
        # Since useSessionStore isn't exposed globally, we can mock it by triggering a click
        # that sets the state, or by injecting a fake WS message if we routed the websocket.
        # Alternatively, let's just use the Calendar UI to start the focus, but mock the start endpoint.

        page.route("**/api/business/me/sessions/start", lambda route: route.fulfill(
            status=200,
            json={"status": "success"}
        ))

        # We can also just mock the websocket since the frontend uses a Mock WebSocket in "pnpm run mock"
        # Wait... the app already has a "pnpm run mock" which sets up a Mock WebSocket.
        # Let's try to just click "Start Focus" on a mocked task.

        # Click today's date in the calendar
        print("Clicking calendar day 1...")
        page.locator(".react-calendar__tile").first.click()
        page.wait_for_timeout(1000)

        print("Adding a task...")
        page.locator("input[placeholder='Add a new task...']").fill("Test Focus Task")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)

        print("Clicking Start Focus...")
        try:
            page.locator("button:has-text('Start Focus')").click(timeout=3000)
        except Exception as e:
            print("Could not click Start Focus normally:", e)
            # Try to force click
            page.evaluate("document.evaluate('//button[contains(., \"Start Focus\")]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click()")

        page.wait_for_timeout(3000)

        # Capture screenshot
        print("Capturing screenshot...")
        page.screenshot(path="slider_active.png")
        print("Done. Screenshot saved to slider_active.png")

        browser.close()

if __name__ == "__main__":
    run()
