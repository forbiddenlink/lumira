# Lumira design

Approved direction: the room. The first screen is a picture and a short name. The studio has one action. Series is a list, not the entrance.

This file records the decisions used in the templates. Tokens already named in `design-system.txt` stay the source of hex values. Do not add a new color.

## Principles

- The newest public work owns the first viewport. Captions sit under the picture.
- A visitor reads a sentence, not a console. Counts, model names, energy, and intensity stay off the wall.
- One primary action in the studio: Let her create. A commission is a quieter form with the same fields.
- A work has one visitor action: Share. File name, prompt, animate, feature, download, and delete sit in a disclosure. Delete stays a danger control inside that disclosure.
- Ask is a control in the page flow. It does not float over titles.
- Page families share the wordmark, Gallery, and Studio. Instruments (classic archive, monitoring, admin) share type and color and do not become the gallery.
- Titles are the first clause of the prompt until a saved title exists. Say so on the work.

## Type, space, surface

- Display: Fraunces. UI: Figtree. Both are already loaded by the gallery, studio, share, privacy, and error pages.
- Page background `--bg-dark`. Panels `--bg-panel`. Raised controls `--bg-elevated`.
- Text `--text-main` on those three backgrounds. Secondary copy `--text-muted` or `--text-faint`. Never the old faint `#6e665c`.
- Accent `--accent` for the primary control, focus ring, and small labels. Mood hues tint atmosphere. Mood words use mixed text color, not the raw mood hex.
- Featured plate: `object-fit: cover`, height `min(72vh, 760px)` on a wide screen and `min(68vh, 520px)` on a phone. Caption is a left-aligned column: kicker, title, source note, mood and date, Open.
- Breaks already in the templates: 900px stacks the studio column; 720px and 768px loosen the gallery chrome. Tabs wrap. They do not clip.
- Radius stays `--radius-sm` 6px, `--radius-md` 10px, `--radius-lg` 16px where a control already uses them. The plate itself stays nearly square-cornered.
- Motion already yields to `prefers-reduced-motion`. No new essential transition.

## Components

- Header: wordmark Lumira, Gallery, Studio, Ask. Phone: Ask stays in flow above the picture, not a fixed bar over the caption.
- Gallery views stay: Recent, Lumira's Picks, By Mood, Evolution, Series. They wrap onto another line instead of scrolling out of sight.
- Cards: short title, mood, date. The full prompt is the title attribute.
- Lightbox: Share is filled brass. Love stays beside it. The rest is "File and tools".
- Missing URL: the designed error page, with Gallery and Studio. API and `/admin/` data responses stay JSON.
- Admin, when data is refused: the key form and a sentence that the console is locked. No env var names.
- Classic `/classic`: archive grid. The three count cards are not the opening. Glass blur is not used for them.

## Original decisions

- Collapsing two create systems into one primary and one quiet form is original. References showed a single request, not this exact split.
- The visitor sentence follows the newest work's mood when the stored statement disagrees. Wording: "She is {mood}, and the newest work carries that mood."
- Titles are derived, not stored. Persistence can come later without changing this display rule.
- `/docs` stays as the API document. CSP blocks its script CDN. The policy is not loosened.

## Implementation map

| Weakness | Where |
| --- | --- |
| W1 plate and caption | `gallery_modern.html` featured work |
| W2 sentence, not telemetry | gallery now-line; studio lock copy |
| W3 one studio action | `lumira.html` create button and request buttons |
| W4 short titles | gallery cards, lightbox, `app.py` share title |
| W5 Ask in flow | `gallery_modern.html` creation control |
| W6 tabs wrap | gallery view tabs |
| W7 shared names | classic, share, error, offline, monitoring, admin |
| W8 designed 404, admin key | `exception_handlers.py`, `app.py`, admin dashboard |
| W9 action weight | lightbox actions |
