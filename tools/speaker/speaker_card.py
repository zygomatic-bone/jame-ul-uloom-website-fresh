"""Renders the NEW profile card that sits directly below the existing Speaker Profile on Bayanath.html.

The existing card (speaker.py, speaker-profile.json) is not touched: this module only adds a second, separate card.
All text, links and photographs come from speaker-card.json and tools/speaker/slides/. Markup only; the look is in
tools/portal-ui/speakercard.css and the behaviour (slideshow, entrance, latest videos) in tools/portal-ui/speakercard.js.
Nothing is hidden without JavaScript: the photographs become a swipeable row, the links are plain anchors and the
"Explore All Channels" panel is a native <details>."""
import json
from html import escape
from pathlib import Path

import speaker

HERE = Path(__file__).resolve().parent
DATA = HERE / 'speaker-card.json'
SLIDE_DIR = HERE / 'slides'
ASSET_DIR = 'portal-assets/speaker/slides/'

# Plain, generic glyphs (not the brands' logos); every one sits beside its text label.
GLYPHS = {
    'youtube': 'M3 7.5A2.5 2.5 0 0 1 5.5 5h13A2.5 2.5 0 0 1 21 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5ZM10 9.2v5.6L15 12Z',
    'linktree': 'M12 3v18M12 8 6 4M12 8l6-4M12 13 5 9M12 13l7-4M12 18l-4-2M12 18l4-2',
    'facebook': 'M9 8a3 3 0 1 0 0-.01M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5M17 9a2.2 2.2 0 1 0 0-.01M16 14.2c2.7 0 4.5 1.7 4.5 4.3',
    'instagram': 'M7 4h10a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3ZM12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM16.8 7.2v.01',
    'x': 'M5 5l14 14M19 5 5 19',
    'whatsapp': 'M4 20l1.2-4A8 8 0 1 1 8 18.8ZM9.5 9c.5 2.5 2.5 4.5 5 5',
    'play': 'M8 5.5v13l11-6.5Z',
    'pause': 'M8 5v14M16 5v14',
    'prev': 'M15 5l-7 7 7 7',
    'next': 'M9 5l7 7-7 7',
    'arrow': 'M7 17 17 7M9 7h8v8',
    'plus': 'M12 5v14M5 12h14',
}


def glyph(name, cls='sc-ico'):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="{GLYPHS[name]}"></path></svg>'


def load():
    return json.loads(DATA.read_text(encoding='utf-8'))


def slide_files():
    return [s['file'] for s in load()['slides']]


def _slides(d):
    from imgutil import image_size
    out, dots = [], []
    n = len(d['slides'])
    for i, s in enumerate(d['slides']):
        w, h = image_size(SLIDE_DIR / s['file'])
        src = f'{ASSET_DIR}{s["file"]}'
        first = i == 0
        out.append(
            f'<figure class="sc-slide{" is-active" if first else ""}" data-dir="{s["dir"]}" role="group" aria-roledescription="slide" aria-label="{i + 1} of {n}">'
            f'<img class="sc-bg" src="{src}" alt="" width="{w}" height="{h}" loading="lazy" decoding="async" aria-hidden="true">'
            f'<img class="sc-img" src="{src}" alt="{escape(s["alt"], quote=True)}" width="{w}" height="{h}" loading="{"eager" if first else "lazy"}" decoding="async">'
            f'</figure>')
        dots.append(f'<button class="sc-dot{" is-active" if first else ""}" type="button" aria-label="Show photograph {i + 1} of {n}"{" aria-current=\"true\"" if first else ""}><i></i></button>')
    return ''.join(out), ''.join(dots)


def render():
    d = load()
    slides, dots = _slides(d)
    n = len(d['slides'])
    roles = ''.join(f'<li class="sc-role">{speaker.icon(r["icon"], "sc-ico")}<span>{escape(r["text"])}</span></li>' for r in d['roles'])
    tags = ''.join(f'<li class="sc-tag">{speaker.icon(c["icon"], "sc-ico sc-ico-sm")}<span>{escape(c["text"])}</span></li>' for c in d['categories'])
    p = d['primary']
    tiles = ''.join(
        f'<li><a class="sc-soc sc-soc-{l["key"]}" href="{escape(l["url"], quote=True)}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{escape(l["label"], quote=True)} (opens in a new tab)">'
        f'<span class="sc-soc-ic">{glyph(l["key"])}</span>'
        f'<span class="sc-soc-tx"><b>{escape(l["label"])}</b><small>{escape(l["sub"])}</small></span>{glyph("arrow", "sc-ico sc-ico-go")}</a></li>'
        for l in d['links'])
    return (
        f'<section class="sc-card" data-no-motion data-speakercard data-interval="{int(d["interval_seconds"])}" aria-labelledby="sc-title">'
        f'<div class="sc-float"><div class="sc-panel"><span class="sc-glow" aria-hidden="true"></span>'
        # ---- slideshow ----
        f'<div class="sc-show" role="group" aria-roledescription="carousel" aria-label="Photographs of the speaker and his programmes" tabindex="0">'
        f'<div class="sc-stage">{slides}</div>'
        f'<div class="sc-ctl" hidden>'
        f'<button class="sc-nav sc-prev" type="button" aria-label="Previous photograph">{glyph("prev")}</button>'
        f'<button class="sc-nav sc-next" type="button" aria-label="Next photograph">{glyph("next")}</button>'
        f'</div>'
        f'<div class="sc-bar" hidden><div class="sc-dots" role="group" aria-label="Choose a photograph">{dots}</div>'
        f'<button class="sc-pp" type="button" aria-pressed="false" aria-label="Pause the slideshow"><span class="sc-pp-pause">{glyph("pause")}</span><span class="sc-pp-play">{glyph("play")}</span></button></div>'
        f'<p class="sc-live" role="status" aria-live="polite"></p>'
        f'</div>'
        # ---- profile ----
        f'<div class="sc-body">'
        f'<p class="sc-eyebrow sc-rise">{escape(d["eyebrow"])}</p>'
        f'<h2 id="sc-title" class="sc-rise">{escape(d["name"])}</h2>'
        f'<ul class="sc-roles sc-rise" aria-label="Roles">{roles}</ul>'
        f'<p class="sc-intro sc-rise">{escape(d["intro"])}</p>'
        f'<p class="sc-bio sc-rise">{escape(d["biography"])}</p>'
        f'<div class="sc-cats sc-rise"><h3 id="sc-cats-t">{escape(d["categories_title"])}</h3><ul class="sc-tags" aria-labelledby="sc-cats-t">{tags}</ul></div>'
        f'<p class="sc-source sc-rise">{escape(d["source_note"])}</p>'
        f'</div>'
        # ---- latest videos (filled by speakercard.js from data/bayanath-videos.json; hidden if it cannot be read) ----
        f'<div class="sc-latest" data-sc-latest data-sc-count="{int(d["latest_count"])}" hidden><h3>{escape(d["latest_title"])}</h3><ul class="sc-vids"></ul></div>'
        # ---- official links, last ----
        f'<div class="sc-links sc-rise">'
        f'<a class="sc-cta" href="{escape(p["url"], quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="{escape(p["label"], quote=True)} (opens in a new tab)">'
        f'<span class="sc-cta-ic">{glyph("youtube")}</span><span class="sc-cta-tx">{escape(p["label"])}</span>{glyph("arrow", "sc-ico sc-ico-go")}</a>'
        f'<details class="sc-more"><summary><span>{escape(d["more_label"])}</span>{glyph("plus", "sc-ico sc-ico-plus")}</summary>'
        f'<ul class="sc-soc-list">{tiles}</ul></details>'
        f'</div>'
        f'</div></div></section>')
