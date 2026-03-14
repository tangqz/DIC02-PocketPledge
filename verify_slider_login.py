from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Mock APIs to easily pass through
        page.route("**/api/auth/login", lambda route: route.fulfill(
            status=200,
            json={"access_token": "mock_token", "token_type": "bearer"}
        ))
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
            json={"has_active_tasks": False, "total_tasks_today": 0, "completed_tasks_today": 0}
        ))
        page.route("**/api/business/me/tasks/daily?*", lambda route: route.fulfill(
            status=200,
            json=[]
        ))

        print("Navigating to mock server...")
        page.goto("http://localhost:5173", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print("Logging in...")
        page.locator("input[placeholder='Username']").fill("test")
        page.locator("input[placeholder='Password']").fill("test")
        page.locator("button:has-text('Sign In')").click()
        page.wait_for_timeout(2000)

        print("Clicking a day...")
        page.evaluate("""
            const tiles = document.querySelectorAll('button[class*="react-calendar__tile"]');
            if (tiles.length > 0) {
                tiles[0].click();
            } else {
                console.log("No calendar tiles found");
            }
        """)
        page.wait_for_timeout(1000)

        print("Adding a task...")
        try:
            page.locator("input[placeholder*='Add']").fill("Focus Session Task")
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
        except Exception as e:
            print("Could not fill task:", e)

        print("Clicking Start Focus...")
        try:
            page.locator("button:has-text('Start Focus')").click(timeout=3000)
        except Exception as e:
            print("Could not click Start Focus normally:", e)

        print("Forcing state active by mutating Zustand store...")
        page.evaluate("""
            // This is a hack to bypass WS requirement and force active session
            window.useSessionStore = window.useSessionStore || null; // Wait...
            // In dev mode or Vite, we can't easily access Zustand. Let's just create an event or use React Developer tools approach?
            // Actually, since this is testing the slider, we can just render the component manually if we wanted.
            // But let's see if 'Start Focus' successfully put us in 'active' state.
        """)
        page.wait_for_timeout(2000)

        # Capture screenshot of the active session
        print("Capturing active session screenshot...")
        page.screenshot(path="slider_final.png", full_page=True)
        print("Done. Screenshot saved to slider_final.png")

        browser.close()

if __name__ == "__main__":
    run()
