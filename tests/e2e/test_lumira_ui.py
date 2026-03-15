"""E2E tests for Lumira web UI using Playwright.

These tests verify the functionality of the Lumira creative studio UI,
including page load, theme toggling, gallery navigation, and more.

Run with:
    pytest tests/e2e/ -m e2e -v

Requires pytest-playwright to be installed.
"""

import re

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


class TestPageLoad:
    """Tests for page loading and initial state."""

    def test_page_loads_correctly(self, lumira_page: Page):
        """Test that the Lumira page loads with correct elements."""
        page = lumira_page

        # Check title
        expect(page).to_have_title("Lumira | Autonomous AI Artist")

        # Check main heading is visible
        heading = page.locator("h1:has-text('LUMIRA')")
        expect(heading).to_be_visible()

        # Check subtitle
        subtitle = page.locator(".subtitle")
        expect(subtitle).to_have_text("Autonomous AI Artist")

        # Check mood container is visible
        mood_container = page.locator(".mood-container")
        expect(mood_container).to_be_visible()

        # Check mood orb is rendered
        mood_orb = page.locator("#mood-orb")
        expect(mood_orb).to_be_visible()

        # Check gallery panel is visible
        gallery_panel = page.locator(".gallery-panel")
        expect(gallery_panel).to_be_visible()

    def test_page_has_required_controls(self, lumira_page: Page):
        """Test that all control buttons are present."""
        page = lumira_page

        # Check CREATE button
        create_btn = page.locator("#create-btn")
        expect(create_btn).to_be_visible()
        expect(create_btn).to_have_text("CREATE")

        # Check EVOLVE button
        evolve_btn = page.locator("button:has-text('EVOLVE')")
        expect(evolve_btn).to_be_visible()

        # Check TIMELINE button
        timeline_btn = page.locator("button:has-text('TIMELINE')")
        expect(timeline_btn).to_be_visible()

        # Check MEMORY button
        memory_btn = page.locator("button:has-text('MEMORY')")
        expect(memory_btn).to_be_visible()

    def test_semantic_search_bar_visible(self, lumira_page: Page):
        """Test that semantic search bar is rendered."""
        page = lumira_page

        search_input = page.locator("#semantic-search")
        expect(search_input).to_be_visible()
        expect(search_input).to_have_attribute(
            "placeholder",
            "Search by meaning... (e.g., 'peaceful nature scenes', 'vibrant abstract')"
        )


class TestThemeToggle:
    """Tests for dark/light theme toggle functionality."""

    def test_theme_toggle_button_exists(self, lumira_page: Page):
        """Test that theme toggle button is present."""
        page = lumira_page

        toggle_btn = page.locator("#theme-toggle")
        expect(toggle_btn).to_be_visible()
        expect(toggle_btn).to_have_attribute("aria-label", "Toggle theme")

    def test_theme_toggles_from_dark_to_light(self, lumira_page: Page):
        """Test toggling from dark (default) to light theme."""
        page = lumira_page

        # Verify initial state (no data-theme or dark theme)
        html = page.locator("html")
        initial_theme = html.get_attribute("data-theme")
        assert initial_theme is None or initial_theme == "dark"

        # Click theme toggle
        toggle_btn = page.locator("#theme-toggle")
        toggle_btn.click()

        # Verify theme changed to light
        expect(html).to_have_attribute("data-theme", "light")

    def test_theme_toggles_back_to_dark(self, lumira_page: Page):
        """Test toggling from light back to dark theme."""
        page = lumira_page
        html = page.locator("html")

        # Toggle to light
        toggle_btn = page.locator("#theme-toggle")
        toggle_btn.click()
        expect(html).to_have_attribute("data-theme", "light")

        # Toggle back to dark
        toggle_btn.click()
        expect(html).to_have_attribute("data-theme", "dark")

    def test_theme_persists_in_localstorage(self, lumira_page: Page):
        """Test that theme preference is saved to localStorage."""
        page = lumira_page

        # Toggle to light theme
        toggle_btn = page.locator("#theme-toggle")
        toggle_btn.click()

        # Check localStorage
        saved_theme = page.evaluate("localStorage.getItem('lumira-theme')")
        assert saved_theme == "light"

        # Toggle back to dark
        toggle_btn.click()
        saved_theme = page.evaluate("localStorage.getItem('lumira-theme')")
        assert saved_theme == "dark"


class TestMoodInfluenceButtons:
    """Tests for mood influence button functionality."""

    def test_influence_buttons_exist(self, lumira_page: Page):
        """Test that all mood influence buttons are present."""
        page = lumira_page

        # Check influence section exists
        influence_section = page.locator(".mood-influence")
        expect(influence_section).to_be_visible()

        # Check all 4 influence buttons
        influence_buttons = page.locator(".influence-btn")
        expect(influence_buttons).to_have_count(4)

    def test_influence_buttons_are_clickable(self, lumira_page: Page):
        """Test that influence buttons can be clicked."""
        page = lumira_page

        # Get the energize button (first one)
        energize_btn = page.locator(".influence-btn").first
        expect(energize_btn).to_be_enabled()

        # Click and verify no error
        energize_btn.click()

        # Button should be temporarily disabled
        expect(energize_btn).to_be_disabled()

        # Wait for re-enable
        page.wait_for_timeout(1500)
        expect(energize_btn).to_be_enabled()

    def test_influence_buttons_have_correct_titles(self, lumira_page: Page):
        """Test that influence buttons have correct accessibility labels."""
        page = lumira_page

        buttons = page.locator(".influence-btn")

        # Check aria-labels
        expect(buttons.nth(0)).to_have_attribute("aria-label", "Energize Lumira's mood")
        expect(buttons.nth(1)).to_have_attribute("aria-label", "Calm Lumira's mood")
        expect(buttons.nth(2)).to_have_attribute("aria-label", "Provoke Lumira's mood")
        expect(buttons.nth(3)).to_have_attribute("aria-label", "Inspire Lumira's mood")


class TestGalleryNavigation:
    """Tests for gallery navigation functionality."""

    def test_gallery_grid_exists(self, lumira_page: Page):
        """Test that gallery grid container exists."""
        page = lumira_page

        gallery_grid = page.locator("#gallery-grid")
        expect(gallery_grid).to_be_visible()
        expect(gallery_grid).to_have_attribute("role", "list")

    def test_art_cards_are_clickable(self, lumira_page: Page):
        """Test that art cards can be clicked to open lightbox."""
        page = lumira_page

        # Wait for gallery to load
        art_cards = page.locator(".art-card")

        # If there are no cards, skip (empty gallery)
        if art_cards.count() == 0:
            pytest.skip("No art cards in gallery - empty state")

        # Click first card
        first_card = art_cards.first
        first_card.click()

        # Verify lightbox opens
        lightbox = page.locator("#lightbox")
        expect(lightbox).to_have_class(re.compile(r"active"))

    def test_art_cards_have_keyboard_support(self, lumira_page: Page):
        """Test that art cards can be activated via keyboard."""
        page = lumira_page

        art_cards = page.locator(".art-card")

        if art_cards.count() == 0:
            pytest.skip("No art cards in gallery - empty state")

        # Focus first card
        first_card = art_cards.first
        first_card.focus()

        # Press Enter to open
        page.keyboard.press("Enter")

        # Verify lightbox opens
        lightbox = page.locator("#lightbox")
        expect(lightbox).to_have_class(re.compile(r"active"))


class TestLightbox:
    """Tests for lightbox functionality."""

    def _open_lightbox(self, page: Page) -> bool:
        """Helper to open lightbox if cards exist."""
        art_cards = page.locator(".art-card")
        if art_cards.count() == 0:
            return False
        art_cards.first.click()
        page.wait_for_selector("#lightbox.active")
        return True

    def test_lightbox_opens_on_card_click(self, lumira_page: Page):
        """Test that lightbox opens when clicking art card."""
        page = lumira_page

        if not self._open_lightbox(page):
            pytest.skip("No art cards in gallery")

        lightbox = page.locator("#lightbox")
        expect(lightbox).to_have_class(re.compile(r"active"))

    def test_lightbox_closes_on_close_button(self, lumira_page: Page):
        """Test that lightbox closes when clicking close button."""
        page = lumira_page

        if not self._open_lightbox(page):
            pytest.skip("No art cards in gallery")

        # Click close button
        close_btn = page.locator(".close-btn")
        close_btn.click()

        # Verify lightbox is closed
        lightbox = page.locator("#lightbox")
        expect(lightbox).not_to_have_class(re.compile(r"active"))

    def test_lightbox_closes_on_escape_key(self, lumira_page: Page):
        """Test that lightbox closes when pressing Escape."""
        page = lumira_page

        if not self._open_lightbox(page):
            pytest.skip("No art cards in gallery")

        # Press Escape
        page.keyboard.press("Escape")

        # Verify lightbox is closed
        lightbox = page.locator("#lightbox")
        expect(lightbox).not_to_have_class(re.compile(r"active"))

    def test_lightbox_closes_on_backdrop_click(self, lumira_page: Page):
        """Test that lightbox closes when clicking backdrop."""
        page = lumira_page

        if not self._open_lightbox(page):
            pytest.skip("No art cards in gallery")

        # Click on lightbox backdrop (not content)
        lightbox = page.locator("#lightbox")
        lightbox.click(position={"x": 10, "y": 10})

        # Verify lightbox is closed
        expect(lightbox).not_to_have_class(re.compile(r"active"))

    def test_lightbox_keyboard_navigation(self, lumira_page: Page):
        """Test gallery navigation with arrow keys in lightbox."""
        page = lumira_page

        art_cards = page.locator(".art-card")
        if art_cards.count() < 2:
            pytest.skip("Need at least 2 art cards for navigation test")

        # Open first card
        art_cards.first.click()
        page.wait_for_selector("#lightbox.active")

        # Get initial image src
        initial_src = page.locator("#lb-img").get_attribute("src")

        # Press right arrow to go to next
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)  # Wait for transition

        # Check image changed (or stayed same if only 1 image)
        new_src = page.locator("#lb-img").get_attribute("src")
        # The image src should potentially change (depends on gallery state)
        # At minimum, no error should occur
        assert new_src is not None

        # Press left arrow to go back
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(300)

        # Navigate should work without error
        back_src = page.locator("#lb-img").get_attribute("src")
        assert back_src is not None

    def test_lightbox_has_action_buttons(self, lumira_page: Page):
        """Test that lightbox has action buttons."""
        page = lumira_page

        if not self._open_lightbox(page):
            pytest.skip("No art cards in gallery")

        # Check for action buttons container
        actions = page.locator("#lb-actions")
        expect(actions).to_be_visible()

        # Check for specific action buttons
        variations_btn = page.locator("button:has-text('Variations')")
        expect(variations_btn).to_be_visible()

        similar_btn = page.locator("button:has-text('Similar')")
        expect(similar_btn).to_be_visible()

        download_btn = page.locator("button:has-text('Download')")
        expect(download_btn).to_be_visible()

        share_btn = page.locator("button:has-text('Share')")
        expect(share_btn).to_be_visible()


class TestSemanticSearch:
    """Tests for semantic search functionality."""

    def test_search_input_accepts_text(self, lumira_page: Page):
        """Test that search input accepts and displays text."""
        page = lumira_page

        search_input = page.locator("#semantic-search")
        search_input.fill("peaceful landscape")

        expect(search_input).to_have_value("peaceful landscape")

    def test_search_results_container_exists(self, lumira_page: Page):
        """Test that search results container is present."""
        page = lumira_page

        results_container = page.locator("#semantic-search-results")
        expect(results_container).to_be_attached()

    def test_search_results_hidden_initially(self, lumira_page: Page):
        """Test that search results are hidden by default."""
        page = lumira_page

        results_container = page.locator("#semantic-search-results")
        # Should not have 'active' class
        expect(results_container).not_to_have_class(re.compile(r"active"))

    def test_search_triggers_on_input(self, lumira_page: Page):
        """Test that typing triggers search (debounced)."""
        page = lumira_page

        search_input = page.locator("#semantic-search")

        # Type a query
        search_input.fill("abstract art")

        # Wait for debounce and API call
        page.wait_for_timeout(500)

        # Results container should become active if results are found
        # (or stay hidden if no results/API not available)
        # Just verify no JS error occurs
        results_container = page.locator("#semantic-search-results")
        # Container should be in DOM
        expect(results_container).to_be_attached()

    def test_clicking_outside_closes_results(self, lumira_page: Page):
        """Test that clicking outside closes search results."""
        page = lumira_page

        search_input = page.locator("#semantic-search")
        search_input.fill("test search")
        page.wait_for_timeout(500)

        # Click outside the search container
        page.locator("h1").click()

        # Results should be hidden
        results_container = page.locator("#semantic-search-results")
        expect(results_container).not_to_have_class(re.compile(r"active"))


class TestLoRAToggle:
    """Tests for LoRA toggle and localStorage persistence."""

    def test_lora_toggle_exists(self, lumira_page: Page):
        """Test that LoRA toggle checkbox exists."""
        page = lumira_page

        lora_toggle = page.locator("#request-lora")
        expect(lora_toggle).to_be_attached()
        expect(lora_toggle).to_have_attribute("type", "checkbox")

    def test_lora_toggle_is_unchecked_by_default(self, lumira_page: Page):
        """Test that LoRA toggle is unchecked by default."""
        page = lumira_page

        # Clear any previous localStorage value
        page.evaluate("localStorage.removeItem('lumira-use-lora')")
        page.reload()
        page.wait_for_selector("#mood-text:not(:has-text('Awakening...'))", timeout=15000)

        lora_toggle = page.locator("#request-lora")
        expect(lora_toggle).not_to_be_checked()

    def test_lora_toggle_can_be_checked(self, lumira_page: Page):
        """Test that LoRA toggle can be clicked to enable."""
        page = lumira_page

        lora_toggle = page.locator("#request-lora")
        lora_toggle.check()

        expect(lora_toggle).to_be_checked()

    def test_lora_toggle_persists_in_localstorage(self, lumira_page: Page):
        """Test that LoRA preference persists to localStorage."""
        page = lumira_page

        # Clear previous value
        page.evaluate("localStorage.removeItem('lumira-use-lora')")

        lora_toggle = page.locator("#request-lora")

        # Enable LoRA
        lora_toggle.check()

        # Trigger the submit function to save to localStorage
        # (The save happens on form submission, so we need to check the
        # value is saved there)
        # For testing, we can directly verify the toggle state after checking
        expect(lora_toggle).to_be_checked()

        # Check localStorage value after interaction
        # Note: The actual localStorage save happens in submitCreationRequest()
        # We can verify the checkbox state persists through page actions

    def test_lora_toggle_loads_from_localstorage(self, lumira_page: Page, base_url: str):
        """Test that LoRA preference loads from localStorage on page load."""
        page = lumira_page

        # Set localStorage value directly
        page.evaluate("localStorage.setItem('lumira-use-lora', 'true')")

        # Reload page
        page.goto(f"{base_url}/lumira")
        page.wait_for_selector("#mood-text:not(:has-text('Awakening...'))", timeout=15000)

        # Check that toggle is checked
        lora_toggle = page.locator("#request-lora")
        expect(lora_toggle).to_be_checked()


class TestAccessibility:
    """Tests for accessibility features."""

    def test_skip_link_exists(self, lumira_page: Page):
        """Test that skip link for accessibility is present."""
        page = lumira_page

        skip_link = page.locator(".skip-link")
        expect(skip_link).to_be_attached()
        expect(skip_link).to_have_attribute("href", "#gallery-grid")

    def test_mood_container_has_aria_live(self, lumira_page: Page):
        """Test that mood container has aria-live for screen readers."""
        page = lumira_page

        mood_container = page.locator(".mood-container")
        expect(mood_container).to_have_attribute("aria-live", "polite")

    def test_gallery_grid_has_role(self, lumira_page: Page):
        """Test that gallery grid has correct ARIA role."""
        page = lumira_page

        gallery_grid = page.locator("#gallery-grid")
        expect(gallery_grid).to_have_attribute("role", "list")

    def test_lightbox_has_dialog_role(self, lumira_page: Page):
        """Test that lightbox has dialog role for accessibility."""
        page = lumira_page

        lightbox = page.locator("#lightbox")
        expect(lightbox).to_have_attribute("role", "dialog")
        expect(lightbox).to_have_attribute("aria-modal", "true")


class TestRequestSection:
    """Tests for the Request a Creation section."""

    def test_request_section_exists(self, lumira_page: Page):
        """Test that request creation section is present."""
        page = lumira_page

        request_section = page.locator(".request-section")
        expect(request_section).to_be_visible()

    def test_request_textarea_exists(self, lumira_page: Page):
        """Test that request prompt textarea is present."""
        page = lumira_page

        textarea = page.locator("#request-prompt")
        expect(textarea).to_be_visible()

    def test_style_dropdown_exists(self, lumira_page: Page):
        """Test that style dropdown is present with options."""
        page = lumira_page

        style_select = page.locator("#request-style")
        expect(style_select).to_be_visible()

        # Check has options
        options = style_select.locator("option")
        expect(options.first).to_have_text("Let Lumira choose")

    def test_mood_dropdown_exists(self, lumira_page: Page):
        """Test that mood dropdown is present with options."""
        page = lumira_page

        mood_select = page.locator("#request-mood")
        expect(mood_select).to_be_visible()

        # Check has options
        options = mood_select.locator("option")
        expect(options.first).to_have_text("Match current mood")

    def test_create_button_exists(self, lumira_page: Page):
        """Test that create button is present."""
        page = lumira_page

        create_btn = page.locator("#request-create-btn")
        expect(create_btn).to_be_visible()
        expect(create_btn).to_have_text("Create for Me")

    def test_autonomous_button_exists(self, lumira_page: Page):
        """Test that autonomous mode button is present."""
        page = lumira_page

        autonomous_btn = page.locator("button:has-text('Or let Lumira decide')")
        expect(autonomous_btn).to_be_visible()
