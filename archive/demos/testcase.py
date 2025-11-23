import re
from playwright.sync_api import Page, expect


def test_example(page: Page) -> None:
    page.goto("http://192.168.100.8/main")
    page.locator(".flex-none.flex > a").first.click()
    page.get_by_role("textbox", name="Name").click()
    page.get_by_role("textbox", name="Name").fill("RX-D46A9121077B")
    page.locator(".btn.btn-outline").first.click()
    page.get_by_role("textbox", name="Name").click(button="right")
    expect(page.locator("html")).to_contain_text("RX-D46A9121077B")
