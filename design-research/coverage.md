# Coverage inventory

Single app: `src/ai_artist/` (Python/FastAPI + Jinja2). No separate frontend package.
Styling lives in per-template `<style>` blocks. Shared tokens are CSS custom properties
copied across templates (canonical names in `lumira.html`). Static assets: `static/`.

Inspection status values: mapped | audited | researched | prototyped | updated | unchanged | blocked.

The room direction was approved and implemented on 2026-09-28 against local `127.0.0.1:8788`. Decisions are in `DESIGN.md`. Baseline shots are in `shots/current/`. After shots are in `shots/final/`. Research log is `log.md`. The direction preview remains in `prototypes/room/index.html`.

| Area | Paths | Status | What changed | Verification | Blockers |
| --- | --- | --- | --- | --- | --- |
| Gallery homepage `/` | `templates/gallery_modern.html` | updated | Newest work is a plate with a short title under it. Ask sits in the page flow. Counts and taste lines are off the wall. Tabs wrap. | Desktop 1440, phone 390, and 800px. No horizontal scroll. Title visible. Empty search still offers Browse all work. | Titles are derived, not saved. |
| Studio `/lumira` | `templates/lumira.html` | updated | One filled action, Let her create. Commission buttons are quiet. Energy and intensity counts are hidden. Lock copy does not name env vars. On a phone the commission panel starts after the mind column. A dropped live link is logged once as “The live link dropped. Trying again.” | Checked at 390 and 1440. Did not submit a generation. Thought stream showed the lock sentence and “Listening for the next impulse…”, with no repeated connection-lost line. | none |
| Share `/share/{id}` | `share.html`, `app.py` | updated | Heading is the first clause of the prompt. Full prompt is in a disclosure. Telemetry curator lines are replaced with a mood sentence. | Opened share `aexhjxjl4rxk`. Title read Cliff. | none |
| Classic `/classic` | `gallery.html` | updated | Archive kept. Count cards hidden. Wordmark and Gallery / Studio links. Warm charcoal and Fraunces. Card lines are still the prompt, because this page is the file record. | Desktop, no horizontal scroll, stats display none. | none |
| Privacy `/privacy` | `privacy.html` | updated | Wordmark reads Lumira. Gallery and Studio links were already there. Policy text unchanged. | Desktop 1440 and phone 390. No horizontal scroll. Heading Privacy Policy. Shots in `shots/final/`. | none |
| Monitoring `/monitoring` | `monitoring.html` | updated | Same charcoal, brass, and type. Title is Monitoring. Still an instrument. | Desktop 1440 and phone 390. No horizontal scroll. Health read Healthy. `/metrics` sample said 503, which is the locked metrics route without a key. | none |
| Admin `/admin/` | `admin/dashboard.html` | updated | When data is refused, the key form is visible with a locked sentence. Gallery and Studio links. | Saw the key field and "Awaiting API key." Did not enter a key. | No API key in this checkout. |
| Error pages | `error.html`, `exception_handlers.py`, `app.py` | updated | Unknown pages render the designed error for browsers, including `*/*`. API and `/admin/` data stay JSON. Studio label matches the rest of the site. | `/this-room-does-not-exist` returned HTML 404 with Gallery and Studio. | none |
| Offline `/offline.html` | `static/offline.html` | updated | Copy no longer says PWA caching. Mark is a frame. Link says Studio. | Desktop 1440 and phone 390. No horizontal scroll. Heading “You're offline”, Try Again, Gallery and Studio. Shots in `shots/final/`. | none |
| WebSocket test | `test_websocket.html` | unchanged | Debug-only. Left out of the public journey. | not opened | intentional |
| API docs `/docs` | FastAPI | blocked | CSP still blocks the docs script. Policy was not loosened. | HTTP 200, page shell only | script CDN remains blocked |
| Machine pages | robots, health, sitemap | unchanged | Not visual. | not part of this pass | intentional |
| Lightbox | `gallery_modern.html` | updated | Share is the filled action. Love sits beside it. File, prompt, animate, feature, download, and delete are in disclosures. | Opened Phoenix. Share was the brass button. | none |
| Commission form | `lumira.html` | updated | Fields and copy kept. Submit is an outline button under Let her create. | Form visible at 1440. Not submitted. | none |
| Empty search | gallery script | unchanged | Existing empty copy still appears. | Searched a nonsense string. Saw Browse all work and Ask Lumira to create this. | none |
| Auth | admin, studio lock | updated | Locked states are sentences. Behavior is still fail-closed. | Admin 503 shows the key form. Studio lock sentence checked. | none |
| Tokens | `DESIGN.md`, `design-system.txt` | updated | No new hex. Monitoring and classic now use the named charcoal, brass, and type. | Keyboard Tab on `/` paints a 2px brass ring immediately on Shortcuts, Templates, Studio, Ask, the plate, tabs, and search. Studio mood buttons do the same in the mood tint. Reduced motion shortens transitions to about 0.01ms. Gallery console had no errors. `tests/e2e/test_a11y.py` passed, including WCAG A/AA on `/`, `/lumira`, `/privacy`, and `/admin/`. Admin Gallery and Studio links are at least 24px tall. | none |
| Icons / images | static, gallery files | unchanged | Real artwork used. Offline mark redrawn with the existing stroke style. | Featured image loaded. | none |

## Journeys to audit

1. Arrive at gallery, read presence, open a work, close it.
2. Switch gallery views (mood, series, evolution) and search.
3. Enter studio, read mood and commission form, do not generate.
4. Open a share link and a missing share.
5. Read privacy, monitoring, classic, admin (unauthenticated), offline, a 404.
