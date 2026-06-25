"""E2E tests for the modern gallery UI."""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestGalleryPageLoad:
    """Tests for gallery homepage."""

    def test_gallery_shell_loads(self, gallery_page: Page):
        page = gallery_page
        expect(page).to_have_title(re.compile(r"Lumira", re.I))
        expect(page.locator("#gallery")).to_be_visible()
        expect(page.locator("#search")).to_be_visible()

    def test_privacy_link_present(self, gallery_page: Page):
        page = gallery_page
        privacy = page.locator('a[href="/privacy"]')
        expect(privacy).to_be_visible()

    def test_llms_txt_endpoint(self, page_with_server: Page, base_url: str):
        page = page_with_server
        response = page.request.get(f"{base_url}/llms.txt")
        assert response.ok
        body = response.text()
        assert "Lumira" in body
        assert "/lumira" in body

    def test_footer_discloses_ai_content(self, gallery_page: Page):
        page = gallery_page
        expect(page.locator("footer")).to_contain_text("AI")


class TestGalleryModal:
    """Tests for image modal accessibility and keyboard behavior."""

    def _open_first_image(self, page: Page) -> bool:
        cards = page.locator(".gallery-item")
        if cards.count() == 0:
            return False
        cards.first.click()
        page.wait_for_selector("#modal.active", timeout=10000)
        return True

    def test_modal_has_dialog_semantics(self, gallery_page: Page):
        page = gallery_page
        page.wait_for_timeout(1500)

        if not self._open_first_image(page):
            pytest.skip("No gallery images available for modal test")

        modal = page.locator("#modal")
        expect(modal).to_have_attribute("role", "dialog")
        expect(modal).to_have_attribute("aria-modal", "true")

    def test_modal_closes_on_escape(self, gallery_page: Page):
        page = gallery_page
        page.wait_for_timeout(1500)

        if not self._open_first_image(page):
            pytest.skip("No gallery images available for modal test")

        page.keyboard.press("Escape")
        expect(page.locator("#modal")).not_to_have_class(re.compile(r"active"))

    def test_modal_close_button_works(self, gallery_page: Page):
        page = gallery_page
        page.wait_for_timeout(1500)

        if not self._open_first_image(page):
            pytest.skip("No gallery images available for modal test")

        page.locator("#modal .modal-close").click()
        expect(page.locator("#modal")).not_to_have_class(re.compile(r"active"))
