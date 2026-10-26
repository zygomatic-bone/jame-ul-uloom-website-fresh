# Notes for contributors

## Basics
- Deploy only `public/`. Generators and sources live in `tools/`. Run `python3 tools/build.py` after every change (it builds everything, then runs the link check and fails if a link or asset is broken). Hand edits to generated HTML, `portal.css`, the copied scripts, `_headers`, `_redirects` and `.htaccess` are overwritten.
- Keep `python3 -I -m unittest discover -s tools/tests` green.
- Static HTML, CSS and JavaScript, as the original site, plus a small PHP layer (`public/api/submit.php`, `jame-server/`) for the forms and the Bayanath updater. No framework or database. The Python in `tools/` is build-time only. PHP stays compatible with 7.4 (no `match`, no `never`, no `str_contains`).
- No inline `<script>` or `style=` attributes: the CSP forbids them. Never add `unsafe-inline`, `unsafe-eval` or another host to the policy without a reason.
- Never crop content photos (`object-fit: cover` only on decorative blurred backdrops). Use lowercase file names. No MP3 audio.
- `index.html` is the only homepage. The old root `home.html` portal page was removed on purpose: never add it back (the generator refuses to). Header logo, "Home" links, breadcrumbs and footers all point to `index.html`.
- Code style of the new files follows the original site: 4 spaces, `selector{` with the brace attached, `function(){`, single quotes, semicolons, ES5 in the scripts that run on every page.

## Where things live
- Residential School pages: `tools/generate_site.py`. Root and institution pages: `tools/generate_portal.py`. Shared CSS and JS: `tools/portal-ui/`, copied to `public/portal-assets/` (the Residential School pages share `app.js`, `theme-init.js`, `motion.js` and `motion.css`).
- One header for the whole site: `tools/site_header.py` is the only definition. Both generators call it; the Residential School passes `home_href='/'`. Never reintroduce a school-specific header or top bar.
- Page text lives in `tools/content_main.py`, `content_more.py` and `content_inst.py`. Edit there, never the HTML. Add a picture by listing it in `tools/recovery_assets.py` (source, destination, alt text, caption) and re-running `import_recovered_assets.py`; every listed picture must be used on a page.
- Copied text: when the original repeated one institution's text on another's page, show it once on the institution it describes and add a redirect in `content_inst.REDIRECTS` (the generator asserts that every redirect target and `#id` exists and that no redirect source is still a file).
- Never merge conflicting historical dates or figures silently, and never describe an institution from text that the original attached to another. Label dated fees, strengths and results with the date the source gives.
- Public wording: do not publish internal notes about where content came from or how it was recovered, scanned-document disclaimers, or audit notices. Keep dated caveats that help a reader.
- Image folder: `public/portal-assets/images/` (the old name `recovered/` must not reappear).

## Do not publish
- Named students' certificates (`NCPUL/images/CERT1.jpeg` is permanently excluded by the owner), anything from the server's private area. Bank details are published only on About Us, from `tools/support/support-details.json` and only while `verified` is true (the owner authorised this in the Speaker Profile brief); the appeal flyer picture itself (`WITHHELD`) stays unpublished, and bank details appear nowhere else. `WITHHELD` in `tools/recovery_assets.py` lists what is held back and why.

## Security rules
- Headers (CSP, framing, `nosniff`, referrer, HSTS, permissions) are defined once in `tools/generate_portal.py` (`CSP`, `CSP_RS`, `SECURITY`) and written to `_headers` and `.htaccess`. `tools/tests/test_security_headers.py` checks them. The Residential School `.htaccess` keeps its own stricter copy; keep the two in sync.
- Do not send the same header from two `_headers` rules (a host may join the values). The Residential School block carries only its extra CSP.
- Build DOM with `textContent` and `createElement`; `innerHTML` only for fixed strings. Never put page data into an HTML string. Validate ids and URLs (see `bayanath.js`).
- External links: `target="_blank"` needs `rel="noopener"`.
- `tools/update_bayanath.py`: fetches only `https` YouTube/Google hosts (or the loopback test server), never follows a redirect off those hosts, caps response size, and never prints or logs the API key (it goes in the `X-Goog-Api-Key` header only). Workflow actions stay pinned to commit hashes. Changes must keep the tests green.

## Bayanath
- `public/Bayanath.html` is generated; cards are drawn by `portal-assets/bayanath.js` from `public/data/bayanath-videos.json`. `tools/update_bayanath.py` (config: `tools/bayanath-config.json`, run by `.github/workflows/update-bayanath.yml` every Saturday 21:00 IST = cron `30 15 * * 6` UTC, plus manual start; staging only) refreshes that file from the YouTube Data API uploads playlist when the secret `YOUTUBE_API_KEY` exists, otherwise from the channel's public RSS feed, and never overwrites it on failure or when nothing changed. Set `playlist_id` in the config if a verified Bayanath playlist exists; otherwise titles are filtered by `title_keywords`.
- New profile card under the Speaker Profile: `tools/speaker/speaker_card.py` + `speaker-card.json` (text, links, slide order) + `portal-ui/speakercard.css/.js`; photographs in `tools/speaker/slides/` are the owner's six supplied files (shown whole; add or reorder only on instruction; never stock photos). Its name, roles and biography are the YouTube channel's own description, supplied by the owner for this card only; that does not lift the rule below for the old card. The old card, `speaker.py`, `speaker-profile.json` and the `sp-` rules in `bayanath.css` must stay byte-identical (`tools/tests/test_speaker_card.py` pins the HTML). Official links are exact; keep `rel="noopener noreferrer"`. No `backdrop-filter` in `speakercard.css` (the aurora behind it moves); transform and opacity only; keep the reduced-motion block; never use `data-count` (app.js turns it into a counter).
- Support Our Mission (About Us): `tools/support/`; never invent or "tidy" bank details, never add a gateway, UPI or donation claims; change the account only in `support-details.json`.
- Speaker Profile: edit `tools/speaker/speaker-profile.json`, never the HTML. The six designation titles and eight area labels are exact wording from the owner; do not reword them. Do not invent biography, credentials, affiliations or languages: `biography` and `languages` stay empty until the owner supplies verified text. Do not show the `verification` notes. The photograph is shown whole.
- `tools/portal-ui/bayanath.css` is scoped under `body.page-bayanath`; no green on this page; keep `backdrop-filter` with the `-webkit-` prefix and the `@supports` fallback, keep the animated layers `pointer-events: none` and transform-only, and keep the `prefers-reduced-motion` block.
- Aurora: CSS gradients moved with transform and opacity only (`.bz-au*`). `portal-ui/aurora.js` sets `--ax --ay --sx --sy` on `.bz-bg`; do not add a `touchmove` listener or per-frame layout reads. The `.bz-au` markup comes from `tools/speaker/speaker.py`. The shared `.ambient` orbs are hidden on this page.

## Jamia Masjid
- Edit `tools/masjid/masjid_page.py` (sections, alt text, order), never `Masjid.html`. Photographs are the owner's files, copied unchanged; do not crop, recompress or rename them without updating `photos-provenance.json` and `MASJID-MEDIA-MAP.md`. The assignment of the Advanced Library, Library and Large Library sections was inferred from the pictures; correct it there if the owner says otherwise.
- Pathway and Water House shows two photographs and all its videos. The Library section (`#library`) replaces the old study-hall name, which must not reappear.
- Videos use `preload="none"`, `muted`, `loop`, `playsinline` and `data-autoplay`; `portal-ui/masjid.js` plays them only while visible. Keep them silent and keep the reduced-motion and data-saving exits. Only the first picture loads eagerly; everything else is lazy.
- The homepage has no B.Com card (do not add one back); the ITI card uses `iti/campus.jpg`, the ITI building.

## Motion and speed
- Motion: edit `portal-ui/motion.css` and `portal-ui/motion.js`, never the copies in `public/`. Hidden start states (`.mo-pre`, `.mo-group`) are added by script only below the fold and removed afterwards; keep that, so no-JS and script failure show everything. Animate transform and opacity only; keep `prefers-reduced-motion` and the `html.mo-lite` (slow device) exits.
- Performance rules: no `filter: blur()` on animated layers, no `mix-blend-mode` full-screen layers, and no `backdrop-filter` on repeated cards (the list is in section 9 of `motion.css`). Keep it only on the header, hero panels, dropdown, drawer and photograph viewer. On screens up to 38rem wide the background orbs do not animate; do not re-enable that without measuring on a phone.
- Photograph viewer: `<a href="image">` links inside `main` open in `dialog.mo-lb`. Do not add `target="_blank"` to them.
- Tall scroll-reveal lists must keep working on phones: `portal-ui/app.js` reveals items taller than the screen as soon as any part is visible.

## Forms, Contact, Feedback, Admissions, Careers
- Pages: `tools/connect/connect_pages.py` (text and markup), `portal-ui/connect.css` (scoped under `body.page-connect`), `portal-ui/forms.js` (ES5, progressive enhancement). Registered in `generate_portal.py` (`CONNECT_PAGES`). Never invent vacancies, fees, dates, opening hours or coordinates, and keep the phone numbers exactly as the owner's Contact page prints them (see the note below).
- The field names, choice values and required fields in the markup must equal `jame-server/forms.php` (`JAME_CHOICES`, `JAME_FORMS`); `tools/tests/test_connect.py` fails if they drift. A form must never show success unless the server answered 200 `{"ok":true}`.
- `jame-server/forms.php` rules: POST only, size cap, Origin/Referer host must be in `allowed_hosts`, honeypot, time trap, rate limits, validation of every field, control characters stripped, the mail subject built from fixed words, Reply-To only after `filter_var`, nothing echoed to the visitor, `no-store`. Do not add file uploads without validation of type, size and content and storage outside the web root.
- `jame-server/bayanath-update.php` mirrors `tools/update_bayanath.py` (same validation and merge rules; keep them in step) and decides the Saturday 21:00 `Asia/Kolkata` slot itself. Tests: `tools/tests/test_bayanath_php.py` (runs the real script against the fake YouTube). Never log or print the API key.
- Open question for the owner: the numbers on the Contact page begin `082…` (for example `0822221151`) while the printed flyer shows 8-digit local numbers (`22221151`). Bangalore's STD code is 080, so the published numbers may be missing a `0` (`08022221151`). They are kept as the owner's page prints them until the owner confirms.
