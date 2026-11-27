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

    def test_welcome_hero_stays_hidden_by_default(self, gallery_page: Page):
        page = gallery_page
        expect(page.locator("#welcome-hero")).to_be_hidden()
        featured = page.locator("#featured-work")
        # Empty gallery: stage stays hidden. Populated: artwork owns the fold.
        expect(featured).to_be_attached()


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


def _boxes_overlap(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


class TestGalleryLayout:
    """Layout regressions that only show up once a dialog is open."""

    @pytest.mark.parametrize("viewport", ["desktop", "mobile"])
    def test_templates_modal_header_and_actions_do_not_collide(
        self, request: pytest.FixtureRequest, viewport: str
    ):
        page = request.getfixturevalue(
            "gallery_page" if viewport == "desktop" else "mobile_page"
        )
        if viewport == "mobile":
            page.goto(f"{request.getfixturevalue('base_url')}/")
            page.wait_for_selector("#gallery", timeout=15000)
        page.evaluate("showTemplatesModal()")
        page.wait_for_selector("#templates-modal.active")

        title = page.locator(".templates-title").bounding_box()
        close = page.locator(".templates-close-btn").bounding_box()
        desc = page.locator(".templates-desc").bounding_box()
        new_btn = page.locator(".templates-new-btn").bounding_box()
        assert title and close and desc and new_btn
        assert not _boxes_overlap(title, close)
        assert not _boxes_overlap(desc, new_btn)
        # The header must span the card, not shrink-wrap its content, so the
        # close button sits clear of the title rather than touching it.
        card = page.locator(".templates-modal-content").bounding_box()
        assert card
        assert close["x"] + close["width"] >= card["x"] + card["width"] - 40

    def test_mobile_zoom_controls_clear_the_info_sheet(
        self, mobile_page: Page, base_url: str
    ):
        page = mobile_page
        page.goto(f"{base_url}/")
        page.wait_for_selector("#gallery", timeout=15000)
        page.wait_for_timeout(1500)
        cards = page.locator(".gallery-item")
        if cards.count() == 0:
            pytest.skip("No gallery images available for modal test")
        cards.first.click()
        page.wait_for_selector("#modal.active", timeout=10000)
        page.wait_for_selector("#modal-info.visible")
        page.wait_for_timeout(500)

        zoom = page.locator(".modal-zoom-controls").bounding_box()
        info = page.locator("#modal-info").bounding_box()
        assert zoom and info
        assert zoom["y"] + zoom["height"] <= info["y"] + 1

    def test_info_toggle_is_not_a_second_close_button(self, gallery_page: Page):
        page = gallery_page
        page.wait_for_timeout(1500)
        cards = page.locator(".gallery-item")
        if cards.count() == 0:
            pytest.skip("No gallery images available for modal test")
        cards.first.click()
        page.wait_for_selector("#modal.active", timeout=10000)

        toggle = page.locator("#modal-info-toggle")
        expect(toggle).to_have_attribute("aria-expanded", "true")
        # Same icon open and closed: an X here reads as a duplicate close.
        assert 'x1="18"' not in toggle.inner_html()

    def test_modal_icon_buttons_have_accessible_names(self, gallery_page: Page):
        page = gallery_page
        for selector in (
            ".modal-zoom-btn",
            "#modal-info-toggle",
            "#modal-prev",
            "#modal-next",
        ):
            buttons = page.locator(selector)
            for index in range(buttons.count()):
                label = buttons.nth(index).get_attribute("aria-label")
                assert label, f"{selector}[{index}] has no aria-label"
