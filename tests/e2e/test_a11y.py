"""Accessibility gate: axe-core WCAG scans plus mobile-only layout checks.

Every finding this file guards against was live in the UI when it was written:
a role="list" grid whose children were all role="button", closed dialogs whose
controls stayed in the tab order, a --text-faint token at 3.36:1, mood chips
that rendered their label in the raw mood hex (2.78:1 on the darker moods),
and links 14px tall. None of it was reachable from the existing suite, which
only ever ran at 1280x720 and only asserted on class names.

The scan runs at both a desktop and a phone viewport because several of these
only reproduced at one of the two.
"""

from typing import Any

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

# WCAG 2.0/2.1 level A and AA. Best-practice rules are deliberately excluded:
# they are advisory, and a gate that fails on advice gets switched off.
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

# Public pages plus the admin shell. /admin/ is reachable unauthenticated by
# design (see ai_artist.web.admin.shell_router) and renders its own chrome.
SCANNED_PATHS = ["/", "/lumira", "/privacy", "/admin/"]

# WCAG 2.2 minimum target size, in CSS pixels.
MIN_TARGET_PX = 24

INTERACTIVE_SELECTOR = (
    'a[href], button, input, select, textarea, [role="button"], '
    '[tabindex]:not([tabindex="-1"])'
)


@pytest.fixture(scope="session")
def axe() -> Axe:
    return Axe()


def _settle(page: Page, base_url: str, path: str) -> None:
    page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate(
        "() => { const el = document.getElementById('page-loader');"
        " if (el) el.classList.add('loaded'); }"
    )


def _format(violations: list[dict[str, Any]]) -> str:
    lines = []
    for v in violations:
        targets = ", ".join(str(n["target"]) for n in v["nodes"][:3])
        lines.append(f"  [{v['impact']}] {v['id']} x{len(v['nodes'])}: {targets}")
        lines.append(f"    {v['help']} -- {v['helpUrl']}")
    return "\n".join(lines)


def _scan(axe: Axe, page: Page, base_url: str, path: str) -> None:
    _settle(page, base_url, path)
    results = axe.run(page, options={"runOnly": {"type": "tag", "values": WCAG_TAGS}})
    violations = results.response["violations"]
    assert not violations, f"axe WCAG A/AA violations on {path}:\n{_format(violations)}"


@pytest.mark.parametrize("path", SCANNED_PATHS)
def test_no_wcag_violations_desktop(
    axe: Axe, page_with_server: Page, base_url: str, path: str
) -> None:
    _scan(axe, page_with_server, base_url, path)


@pytest.mark.parametrize("path", SCANNED_PATHS)
def test_no_wcag_violations_mobile(
    axe: Axe, mobile_page: Page, base_url: str, path: str
) -> None:
    _scan(axe, mobile_page, base_url, path)


@pytest.mark.parametrize("path", SCANNED_PATHS)
def test_no_horizontal_overflow_on_mobile(
    mobile_page: Page, base_url: str, path: str
) -> None:
    """A phone should never scroll sideways to read the page."""
    _settle(mobile_page, base_url, path)
    widths = mobile_page.evaluate(
        "() => ({ scroll: document.documentElement.scrollWidth,"
        " client: document.documentElement.clientWidth })"
    )
    offenders = mobile_page.evaluate("""() => {
            const limit = document.documentElement.clientWidth + 1;
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.right > limit) {
                    out.push(el.tagName + '.' + (el.className || '').toString().split(' ')[0]);
                }
            });
            return out.slice(0, 8);
        }""")
    assert widths["scroll"] <= widths["client"] + 1, (
        f"{path} scrolls horizontally at 390px "
        f"({widths['scroll']}px content in {widths['client']}px): {offenders}"
    )


@pytest.mark.parametrize("path", SCANNED_PATHS)
def test_touch_targets_meet_minimum_size(
    mobile_page: Page, base_url: str, path: str
) -> None:
    """WCAG 2.2 target size (minimum), which axe-core 4.x does not check."""
    _settle(mobile_page, base_url, path)
    undersized = mobile_page.evaluate(
        """(args) => {
            const [selector, min] = args;
            const out = [];
            document.querySelectorAll(selector).forEach(el => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                // Scroll containers carry tabindex so keyboard users can pan
                // them (axe's scrollable-region-focusable). They are not
                // pointer targets, so target-size does not apply.
                const scrollable =
                    /(auto|scroll)/.test(cs.overflowY + cs.overflowX) &&
                    !el.matches('a[href], button, input, select, textarea, [role="button"]');
                if (scrollable) return;
                const r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return;
                if (r.width < min || r.height < min) {
                    out.push({
                        tag: el.tagName,
                        text: (el.textContent || '').trim().slice(0, 30),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                    });
                }
            });
            return out;
        }""",
        [INTERACTIVE_SELECTOR, MIN_TARGET_PX],
    )
    assert not undersized, f"{path} has targets under {MIN_TARGET_PX}px: {undersized}"


@pytest.mark.parametrize("path", ["/lumira", "/"])
def test_closed_dialogs_are_not_in_the_tab_order(
    page_with_server: Page, base_url: str, path: str
) -> None:
    """A dialog faded to opacity 0 must not still be tabbable behind the page."""
    _settle(page_with_server, base_url, path)
    tabbable = page_with_server.evaluate(
        """(selector) => {
            const shown = el => {
                const cs = getComputedStyle(el);
                return cs.visibility !== 'hidden' && cs.display !== 'none';
            };
            const out = [];
            document.querySelectorAll('#lightbox, #explore-modal, #creating-overlay')
                .forEach(dialog => {
                    if (dialog.classList.contains('active')) return;
                    dialog.querySelectorAll(selector).forEach(el => {
                        let node = el;
                        while (node && node !== document.body) {
                            if (!shown(node)) return;
                            node = node.parentElement;
                        }
                        out.push(dialog.id + ' > ' + el.tagName);
                    });
                });
            return out;
        }""",
        INTERACTIVE_SELECTOR,
    )
    assert (
        not tabbable
    ), f"{path} leaves controls tabbable inside closed dialogs: {tabbable}"
