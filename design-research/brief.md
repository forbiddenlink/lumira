# Design brief

Audit date: 2026-09-28. Local checkout served at `http://127.0.0.1:8788` (this working tree, not a deployed build). `api_keys_configured=False`, so generation is locked. The gallery database held 1329 artworks and 1300 themes. Screenshots: `design-research/shots/current/`. Browser capability check: `design-research/shots/00-browser-test.png` (privacy page).

A stale service worker for another app was registered on port 8765 in the browser profile. The audit used port 8788 to avoid it.

## Audience and primary goals

From `.impeccable.md`, not from analytics:

- Primary: Elizabeth, in the studio, asking for work, nudging mood, watching Lumira think.
- Secondary: a visitor who should feel they entered an artist's room, not an admin console.

The job is to see the work, sense the mood, and create with her, without living inside telemetry.

## Page families

| Family | Route | Purpose |
| --- | --- | --- |
| Gallery | `/` | Public wall. Latest work, a "now" strip, collection views, search, lightbox. `/?about=1` adds a statement. |
| Studio | `/lumira` | Commission, mood nudge, thought stream, recent creations. |
| Share | `/share/{id}` | One public work, prompt, curator line, copy link. Missing id uses the error template. |
| Classic | `/classic` | Older grid with three count cards. In the sitemap, not the gallery header. |
| Privacy | `/privacy` | Policy. |
| Monitoring | `/monitoring` | Operator health board. |
| Admin | `/admin/` | Operator shell. Data calls returned HTTP 503 and the key form stayed hidden. |
| Error | `error.html` via missing share | Designed 404. Unknown paths such as `/this-route-does-not-exist` return JSON `{"detail":"Not Found"}`. |
| Offline | `/offline.html` | PWA fallback. |
| API docs | `/docs` | Swagger shell. Rendered as an empty dark page. The bundle is loaded from `cdn.jsdelivr.net`, which the page CSP does not allow. |
| WebSocket test | `/test/websocket` | Debug only. Excluded from the visual pass. |

## Brand qualities worth preserving

Observed in the templates and in `.impeccable.md`:

- Warm charcoal field (`#12100e` and nearby), brass accent, Fraunces for display, Figtree for UI.
- Artwork is already the strongest visual on the page. The snow valley and the cliff share image carry the mood better than any chrome.
- The artist statement on `/?about=1` is in Lumira's voice and is worth reading.
- "About Lumira" already hides XP, style bars, and OCEAN on the studio.
- Skip links, named controls, and a brass `:focus-visible` rule exist. Axe-core covers `/`, `/lumira`, `/privacy`, and `/admin/`.

## Stack and constraints

FastAPI + Jinja2. CSS lives in each template, not a shared stylesheet. No component library. No inline `on*` handlers. Every inline script needs `nonce="{{ csp_nonce }}"`. Text tokens must clear 4.5:1 on `--bg-dark`, `--bg-panel`, and `--bg-elevated`. Mood hues are tints, not text colors. Do not add a frontend framework.

## Strengths

- The palette and type already reject the purple-dashboard look the principles ban.
- The lightbox puts the image on the left and the record on the right. That split is the clearest layout on the site.
- Search with no matches explains itself and offers "Browse all work" and "Ask Lumira to create this".
- Mobile pages measured at 390px did not grow a horizontal page scrollbar (`scrollWidth` matched `innerWidth` on gallery, studio, share, classic, privacy, monitoring, admin, error, and offline).
- Studio commission copy is already human: "Offer a vision. Lumira will interpret it through her present mood and taste."

## Weaknesses

### W1. The newest work does not own the room

Evidence: `current-gallery-desktop.png`, `current-gallery-mobile.png`.

At 1440 the featured frame sits in a left column. The title is the raw prompt, and on first paint the fixed "Ask Lumira" button covered the middle of that title. On a 390px width the image is a square with side padding, and the same button covers the "now" line.

Judgment: a visitor meets chrome and a prompt string before they meet a picture at full presence.

### W2. "Now" reads as a status console

Evidence: gallery mid-scroll (captured in the session; the line is also in `current-gallery-about-desktop.png` and `current-gallery-mobile-mid.png`). Studio: `current-studio-desktop.png`.

Observed strings included "Energy: 20%, Intensity: 50%", "413 tastes learned · learning dreamshaper-8", a critic sentence, and in the studio thought stream "creation is locked until auth is configured (LUMIRA_DEV_MODE=1 or" plus "Connection lost, reconnecting…". Intensity was printed twice in the mood block.

Judgment: the living artist is buried under model names and operator errors.

### W3. The studio has two create systems and a flat action row

Evidence: `current-studio-desktop.png`, `current-studio-mobile.png`.

"LET HER CREATE" sits in the left rail. "Create for Me" sits in a row with Quick Preview, Explore, Animate Latest, Share as Lumira, and "Or let Lumira decide". On a 390px width the commission panel starts at about y=422 and paints over the thought stream (stream top was y=483). Dialogue, statement, and series collapse to a few pixels of height.

Judgment: Elizabeth cannot tell which action is the one that matters, and on a phone the mind disappears under the form.

### W4. Works are titled with prompts

Evidence: gallery cards, lightbox (`current-gallery-lightbox-desktop.png`), share (`current-share-desktop.png`, `current-share-mobile.png`).

Cards, the viewer, and the share page lead with strings such as "phoenix, atmospheric, rainbow hues, masterpiece…". The lightbox also shows `File: var_5c3e8cfe_….png` and `Dimensions: N/A × N/A`.

Judgment: the prompt is process, not the name of the piece. It makes 1,329 works feel like a generation log.

### W5. The floating "Ask Lumira" button covers content

Evidence: featured title, first grid card, view tabs, footer, and the mobile "now" line.

Judgment: a persistent button is useful. Its current position is not.

### W6. Gallery controls crowd the collection, and mobile tabs clip

Evidence: `current-gallery-mobile-mid.png`.

Below the "now" strip, five view tabs run in one row. "Evolution" and "Series" are cut at the edge of the 390px layout (the page itself does not scroll sideways; the tab row is clipped). Search, sort, Filters, and four density buttons then stack before the next image.

Judgment: the second work is too far from the first, and two views are hard to reach by touch.

### W7. Each page invents its own header

Evidence: gallery, studio, share, classic, privacy, monitoring, admin, error, offline.

Classic opens with three count cards (`current-classic-desktop.png`, `current-classic-mobile.png`). That pattern is the one `.impeccable.md` calls an anti-reference. Nav labels differ ("Studio" vs "Creative Studio" vs "Enter the studio").

Judgment: the site does not feel like one place.

### W8. Failure states talk like a server

Evidence: unknown URL returns JSON. Admin shows "Could not load: HTTP 503" and keeps `#auth` hidden (`current-admin-desktop.png`). `/docs` is a blank `#swagger-ui` because the CDN script never runs (`current-docs-desktop.png`). Share 404 and offline are designed and readable.

Judgment: the designed error page is fine. The routes that miss it are not.

### W9. The artwork viewer mixes visitor and operator actions

Evidence: `current-gallery-lightbox-desktop.png`.

Love, Share, Share as Lumira, Animate, Feature, Download, and Delete are the same full-width buttons. Delete is the only one in red.

Judgment: a visitor and the artist-operator are the same UI. Destructive and generative actions should not share that row.

## What success looks like

- One work fills the opening view, with a short human line (mood, and a title when one exists) and the prompt available but not in charge.
- The "now" line is a sentence in her voice. Counts, model names, and auth errors stay in monitoring or a quiet notice.
- The studio has one primary act. Thoughts stay readable on a phone.
- Gallery, studio, share, and privacy share one navigation.
- "Ask Lumira" never covers a title, a tab, or a picture.
- Mobile view tabs can be reached without clipping.
- Empty, missing, and locked states use the same voice as the designed 404.

## Assumptions

- Titles can be derived from tags or the first clause of a prompt when no title field exists. This is a design proposal, not a claim that the database has titles.
- Elizabeth is the only person who creates. Visitors browse and may request work when generation is unlocked. No accounts were found.
- Monitoring and admin should stay plain instruments. They should share type and color, not become gallery pages.
- No traffic or preference data was available. Priority follows the written audience and what the screenshots show.

## Observation vs judgment

Observations are the strings, overlaps, measurements, and screenshots above. Judgments are the "judgment" lines. The success section is a proposal.
