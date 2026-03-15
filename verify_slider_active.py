from playwright.sync_api import sync_playwright

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=2,
        )
        page = context.new_page()

        # Intercept auth and config APIs FIRST, before any load
        page.route("**/api/auth/me", lambda route: route.fulfill(
            status=200,
            json={
                "id": 123,
                "email": "test@example.com",
                "wallet": {"balance": 3000, "charity_ratio": 40}
            }
        ))

        page.route("**/api/business/me/settings/charity-ratio", lambda route: route.fulfill(
            status=200,
            json={"status": "success"}
        ))

        # Set mocked auth to bypass login
        page.goto("http://localhost:5173", wait_until="commit")
        page.evaluate('''() => {
            localStorage.setItem('sb_token', 'mock_token');
        }''')

        page.goto("http://localhost:5173", wait_until="load")

        print("Waiting for page load...")
        page.wait_for_timeout(3000)

        # We changed sessionStore to default to "active" so the slider should be visible immediately
        print("Taking screenshot of the active view...")
        page.screenshot(path="slider_forced_active.png")

        browser.close()

verify()
