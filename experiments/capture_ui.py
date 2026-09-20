"""Capture review screenshots from a running local Compose stack."""

from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("docs/screenshots")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path="/usr/bin/google-chrome",
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto("http://127.0.0.1:8000/register")
        page.fill("[name=full_name]", "Visual Review")
        page.fill("[name=email]", f"visual-{uuid4()}@example.com")
        page.fill("[name=password]", "correct horse battery staple")
        page.get_by_role("button", name="Создать аккаунт").click()

        page.goto("http://127.0.0.1:8000/templates/new")
        page.fill("[name=name]", "Demo contact")
        page.fill("[name=full_name]", "Example Owner")
        page.fill("[name=email]", "owner@example.com")
        page.get_by_role("button", name="Сохранить").click()

        page.goto("http://127.0.0.1:8000/tasks/new")
        page.fill("[name=name]", "Example.com safety check")
        page.fill("[name=urls]", "https://example.com")
        page.select_option("[name=template_id]", label="Demo contact")
        page.get_by_role("button", name="Создать").click()
        page.get_by_role("button", name="Start").click()
        page.wait_for_selector(".badge.completed", timeout=60_000)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=output / "task-run-success.png", full_page=True)

        page.goto("http://127.0.0.1:8000/dashboard")
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=output / "dashboard.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
