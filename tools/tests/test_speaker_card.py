"""The new profile card under the existing Speaker Profile (tools/speaker/speaker_card.py) and the "Support Our Mission" card on
About Us (tools/support/support_card.py).

The brief's first rule: the existing speaker card is not changed. tools/tests/fixtures/speaker-card-original.html is the existing card's
HTML as it was in jameululoom_phase9_4_complete_website_r2.zip, byte for byte. If the owner edits speaker-profile.json on purpose,
regenerate that fixture from speaker.render(); an accidental change fails here.
Run after python3 tools/build.py (the built pages in public/ are checked)."""
import json, re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUB = ROOT / 'public'
for sub in ('speaker', 'support', 'connect', ''):
    sys.path.insert(0, str(ROOT / 'tools' / sub) if sub else str(ROOT / 'tools'))
import speaker, speaker_card, support_card   # noqa: E402
from imgutil import image_size   # noqa: E402

FIXTURE = (ROOT / 'tools' / 'tests' / 'fixtures' / 'speaker-card-original.html').read_text(encoding='utf-8')
LINKS = ['https://www.youtube.com/@MuftiMaqsoodImran', 'https://linktr.ee/MuftiMaqsoodImran', 'https://www.facebook.com/MuftiMaqsoodImran',
         'https://www.instagram.com/muftimaqsoodimran', 'https://x.com/maqsoodimran', 'https://chat.whatsapp.com/C2AGE85WofaEseRcOpnddp']


def built(name):
    return (PUB / name).read_text(encoding='utf-8')


class ExistingCardIsUntouched(unittest.TestCase):
    def test_existing_card_html_is_byte_identical_to_the_original(self):
        self.assertEqual(speaker.render(), FIXTURE)

    def test_existing_card_keeps_all_designations_and_content(self):
        html = speaker.render()
        for t in ('Chief Imam &amp; Khateeb', 'Principal', 'Member, Imarat-e-Shariah, Karnataka', 'Convener, Karnataka Moon Sighting Committee'):
            self.assertIn(t, html)
        self.assertEqual(html.count('class="sp-d"'), 6)

    def test_the_new_card_sits_directly_below_the_existing_one_on_the_page(self):
        page = built('Bayanath.html')
        self.assertIn(speaker.render() + speaker_card.render(), page)   # same container, new card immediately after
        self.assertEqual(page.count('class="sp-card"'), 1)
        self.assertEqual(page.count('class="sc-card"'), 1)

    def test_the_existing_card_and_video_styles_are_not_edited_by_the_new_stylesheet(self):
        css = (ROOT / 'tools' / 'portal-ui' / 'speakercard.css').read_text(encoding='utf-8')
        # the only rules that reach the existing card are the two column-layout rules documented at the top of the file
        reach = [l for l in css.splitlines() if '.sp-card' in l and not l.strip().startswith('/*')]
        self.assertEqual(len(reach), 1)
        self.assertIn('flex: 0 0 auto', reach[0])


class NewCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = speaker_card.load()
        cls.html = speaker_card.render()

    def test_all_six_official_links_are_exact_and_open_safely(self):
        hrefs = re.findall(r'<a class="sc-(?:cta|soc[^"]*)" href="([^"]+)" target="_blank" rel="([^"]+)"', self.html)
        self.assertEqual([h for h, _ in hrefs], LINKS)
        self.assertTrue(all('noopener' in r for _, r in hrefs))
        self.assertEqual(len(re.findall(r'<a [^>]*href="https?://', self.html)), 6)   # no other external link

    def test_the_youtube_button_is_primary_and_the_other_channels_are_in_an_expandable_panel(self):
        self.assertIn('Watch Lectures on YouTube', self.html)
        self.assertIn('Explore All Channels', self.html)
        self.assertLess(self.html.index('sc-cta'), self.html.index('<details class="sc-more"'))
        self.assertEqual(self.html.count('class="sc-soc '), 5)

    def test_official_wording(self):
        self.assertIn('Discover inspiring lectures, authentic Islamic guidance, and educational talks rooted in the Qur’an and Sunnah.', self.html)
        self.assertIn('Islamic scholar, speaker, author, and educator dedicated to sharing Islamic knowledge with wisdom, knowledge, and compassion.', self.html)
        self.assertIn('Imam &amp; Khateeb of Jamia Masjid Bengaluru City', self.html)
        self.assertIn('Chief Principal of Jamia-ul-Uloom Arabic College, Bengaluru', self.html)

    def test_order_slideshow_then_profile_then_latest_then_links(self):
        marks = ['class="sc-show"', 'class="sc-body"', 'data-sc-latest', 'class="sc-links']
        pos = [self.html.index(m) for m in marks]
        self.assertEqual(pos, sorted(pos))
        self.assertLess(self.html.index('class="sc-bio'), self.html.index('class="sc-links'))

    def test_only_the_six_supplied_photographs_are_used_and_they_exist_unchanged(self):
        srcs = set(re.findall(r'<img [^>]*src="([^"]+)"', self.html))
        files = {s.rsplit('/', 1)[1] for s in srcs}
        self.assertEqual(len(files), 6)
        self.assertEqual(files, {p.name for p in speaker_card.SLIDE_DIR.iterdir()})
        for f in files:
            self.assertEqual((speaker_card.SLIDE_DIR / f).read_bytes(), (PUB / 'portal-assets' / 'speaker' / 'slides' / f).read_bytes())
        for s in self.d['slides']:   # width/height attributes match the real pictures (no layout shift, no distortion)
            w, h = image_size(speaker_card.SLIDE_DIR / s['file'])
            self.assertIn(f'src="portal-assets/speaker/slides/{s["file"]}" alt="{s["alt"]}" width="{w}" height="{h}"', self.html)

    def test_every_photograph_has_a_description_and_the_first_loads_eagerly(self):
        main = re.findall(r'<img class="sc-img" [^>]*alt="([^"]+)"[^>]*loading="(\w+)"', self.html)
        self.assertEqual(len(main), 6)
        self.assertEqual([m[1] for m in main], ['eager'] + ['lazy'] * 5)
        self.assertEqual(len(re.findall(r'class="sc-bg" src="[^"]+" alt=""', self.html)), 6)   # backdrop copies are decorative

    def test_slideshow_pace_is_slow(self):
        self.assertGreaterEqual(self.d['interval_seconds'], 8)
        self.assertLessEqual(self.d['interval_seconds'], 12)

    def test_the_scripts_inject_no_html_and_the_css_uses_no_backdrop_blur(self):
        js = (ROOT / 'tools' / 'portal-ui' / 'speakercard.js').read_text(encoding='utf-8')
        for bad in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'eval(', 'document.write'):
            self.assertNotIn(bad, js)
        css = (ROOT / 'tools' / 'portal-ui' / 'speakercard.css').read_text(encoding='utf-8')
        self.assertNotIn('backdrop-filter', css)
        self.assertIn('prefers-reduced-motion: reduce', css)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)')", js)

    def test_video_ids_and_thumbnails_are_validated_like_the_video_list(self):
        js = (ROOT / 'tools' / 'portal-ui' / 'speakercard.js').read_text(encoding='utf-8')
        by = (ROOT / 'tools' / 'portal-ui' / 'bayanath.js').read_text(encoding='utf-8')
        self.assertIn('/^[A-Za-z0-9_-]{11}$/', js)
        self.assertIn(r"/^https:\/\/(?:i\d?\.ytimg\.com|img\.youtube\.com)\//", js)
        self.assertIn(r'/^[A-Za-z0-9_-]{11}$/', by)
        self.assertNotIn('data-count', self.html)   # app.js animates [data-count] elements as counters

    def test_no_video_resources_before_interaction(self):
        self.assertNotIn('<iframe', self.html)
        self.assertNotIn('youtube-nocookie', self.html)
        self.assertNotIn('<video', self.html)

    def test_the_page_loads_the_new_assets_and_they_are_shipped(self):
        page = built('Bayanath.html')
        for a in ('portal-assets/speakercard.css', 'portal-assets/speakercard.js'):
            self.assertIn(a, page)
            self.assertTrue((PUB / a).is_file())
        self.assertLess(page.index('portal-assets/bayanath.css'), page.index('portal-assets/speakercard.css'))
        self.assertNotIn('speakercard', built('index.html'))   # nothing leaks onto other pages


class SupportCard(unittest.TestCase):
    def test_about_us_keeps_its_whole_body_and_gains_the_support_section_after_it(self):
        import content_main
        old = content_main.ROOT['AboutUs.html'][1]
        page = built('AboutUs.html')
        inner = old.split('</p>', 2)[-1]   # past the eyebrow, title and lede that the page template re-wraps
        self.assertIn(inner, page)
        self.assertLess(page.index(inner), page.index('id="support"'))
        self.assertEqual(page.count('Support Our Mission'), 1)
        self.assertIn('Your support helps us continue our educational mission and serve our community. We are grateful for every contribution and every person who stands with us.', page)

    def test_the_verified_details_are_published_on_about_us_only(self):
        d = support_card.load()
        self.assertTrue(support_card.usable(d))
        page = built('AboutUs.html')
        for k, _ in support_card.FIELDS:
            self.assertIn(d[k].replace('&', '&amp;'), page)
        for p in PUB.glob('**/*.html'):
            if p.name != 'AboutUs.html':
                self.assertNotIn(d['account_number'], p.read_text(encoding='utf-8'), p.name)

    def test_formats(self):
        d = support_card.load()
        self.assertRegex(d['account_number'], r'^[0-9]{9,18}$')
        self.assertRegex(d['ifsc'], r'^[A-Z]{4}0[A-Z0-9]{6}$')
        self.assertEqual(d['ifsc'][:4], 'CNRB')   # Canara Bank's code

    def test_details_are_withheld_unless_verified_complete_and_well_formed(self):
        good = support_card.load()
        self.assertTrue(support_card.usable(good))
        for change in ({'verified': False}, {'verified': 'yes'}, {'account_number': ''}, {'ifsc': 'cnrb0000410'}, {'account_number': '12AB'}, {'bank': '  '}):
            d = dict(good); d.update(change)
            self.assertFalse(support_card.usable(d), change)
        d = dict(good); del d['branch']
        self.assertFalse(support_card.usable(d))

    def test_a_withdrawn_card_shows_no_numbers_and_no_placeholders(self):
        orig = support_card.load
        try:
            support_card.load = lambda: dict(orig(), verified=False)
            html = support_card.render('jamiaululoom@gmail.com')
        finally:
            support_card.load = orig
        self.assertIn('Support Our Mission', html)
        self.assertNotRegex(html, r'\d{9}')
        self.assertNotIn('sup-copy', html)
        self.assertNotIn('IFSC', html)
        self.assertIn('mailto:jamiaululoom@gmail.com', html)

    def test_no_payment_gateway_form_or_external_script(self):
        html = support_card.render('jamiaululoom@gmail.com')
        for bad in ('<form', '<input', '<script', 'razorpay', 'paypal', 'upi://', 'Pay now', 'Donate now'):
            self.assertNotIn(bad, html)
        self.assertIn('does not take online payments', html)

    def test_the_support_assets_load_on_about_us_only(self):
        self.assertIn('portal-assets/support.css', built('AboutUs.html'))
        self.assertNotIn('support.css', built('Contact.html'))
        for a in ('support.css', 'support.js'):
            self.assertTrue((PUB / 'portal-assets' / a).is_file())

    def test_the_withheld_flyer_image_stays_out_of_the_site(self):
        self.assertFalse(list(PUB.glob('**/home.jpg')), 'the appeal flyer image itself is not published')


if __name__ == '__main__':
    unittest.main()
