"""The Contact, Feedback, Admissions and Careers pages must agree with the PHP form handler (jame-server/forms.php):
same form names, same field names, same choice values. A mismatch would make a form that looks fine but is always refused."""
import re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHP = (ROOT / 'jame-server' / 'forms.php').read_text(encoding='utf-8')
PUB = ROOT / 'public'
sys.path.insert(0, str(ROOT / 'tools' / 'connect'))
import connect_pages as C


def php_choices():
    block = PHP[PHP.index('const JAME_CHOICES'):PHP.index('/* field =>')]
    out = {}
    for name, body in re.findall(r"'(\w+)' => \[(.*?)\],\n", block, re.S):
        out[name] = re.findall(r"'([\w-]+)' => '", body)
    return out


def php_fields():
    out = {}
    for form in ('feedback', 'admissions', 'careers'):
        start = PHP.index("'fields' => [", PHP.index(f"    '{form}' => ['label'"))
        end = PHP.index("'min' =>", start)
        out[form] = set(re.findall(r"^\s+'(\w+)'\s*=> \[", PHP[start:end], re.M))
    return out


def page(name):
    return (PUB / name).read_text(encoding='utf-8')


class Connect(unittest.TestCase):
    def test_choice_lists_match_the_server(self):
        server = php_choices()
        for name, items in C.CHOICES.items():
            self.assertEqual([v for v, _ in items], server[name], name)

    def test_every_form_field_exists_on_the_server_and_every_required_one_is_in_the_form(self):
        fields = php_fields()
        for kind, file in (('feedback', 'Feedback.html'), ('admissions', 'Admissions.html'), ('careers', 'Careers.html')):
            html = page(file)
            form = re.search(r'<form[^>]*data-cx-form="%s".*?</form>' % kind, html, re.S).group(0)
            names = set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="(\w+)"', form)) - {'form', 'opened', 'website'}
            self.assertEqual(names, fields[kind], kind)
            self.assertIn('name="website"', form)   # honeypot
            self.assertIn('method="post"', form)
            self.assertIn('action="api/submit.php"', form)
            self.assertIn(f'name="form" value="{kind}"', form)

    def test_required_attributes_match_the_servers_required_fields(self):
        required = {}
        for kind in ('feedback', 'admissions', 'careers'):
            start = PHP.index("'fields' => [", PHP.index(f"    '{kind}' => ['label'"))
            end = PHP.index("'min' =>", start)
            required[kind] = set(re.findall(r"^\s+'(\w+)'\s*=> \[[^,]+, true,", PHP[start:end], re.M))
        for kind, file in (('feedback', 'Feedback.html'), ('admissions', 'Admissions.html'), ('careers', 'Careers.html')):
            form = re.search(r'<form[^>]*data-cx-form="%s".*?</form>' % kind, page(file), re.S).group(0)
            marked = set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="(\w+)"[^>]*\srequired', form)) | set(re.findall(r'<(?:input|select|textarea)[^>]*\srequired[^>]*\sname="(\w+)"', form))
            self.assertEqual(marked, required[kind], kind)

    def test_the_requested_wording_is_present(self):
        fb = page('Feedback.html')
        self.assertIn('<h1>Your Voice Matters. Your Thoughts Inspire Us.</h1>', fb)
        self.assertIn('Thank You for Being Part of Our Journey 💙', fb)
        self.assertIn('Your thoughts help us grow, improve, and serve our community better. We truly appreciate you taking the time to share them with us.', fb)
        self.assertIn('Every Great Journey Begins With a First Step.', page('Admissions.html'))
        self.assertIn('Build Your Future. Make a Difference.', page('Careers.html'))

    def test_no_invented_vacancies_and_no_bank_details(self):
        self.assertIn('No specific vacancies are published', page('Careers.html'))
        for f in ('Contact.html', 'Feedback.html', 'Admissions.html', 'Careers.html'):
            t = page(f).lower()
            for word in ('ifsc', 'account number', 'a/c no', 'savings account'):
                self.assertNotIn(word, t, f)

    def test_the_forms_never_claim_to_be_an_application_and_say_what_they_are(self):
        self.assertIn('not an application', page('Admissions.html'))
        self.assertIn('not a job application', page('Careers.html'))

    def test_pages_load_their_own_assets_and_nothing_inline(self):
        for f in ('Contact.html', 'Feedback.html', 'Admissions.html', 'Careers.html'):
            html = page(f)
            self.assertIn('portal-assets/connect.css', html, f)
            self.assertIn('portal-assets/forms.js', html, f)
            self.assertIn('class="page-connect"', html, f)
            self.assertEqual(re.findall(r'<script(?![^>]*\ssrc=)[^>]*>', html), [], f)
            self.assertNotIn(' style=', html, f)
        self.assertNotIn('forms.js', page('Bayanath.html'))

    def test_feedback_is_in_the_menu_and_footer_of_every_root_page(self):
        for f in ('index.html', 'Contact.html', 'Transport.html'):
            self.assertIn('href="Feedback.html"', page(f), f)

    def test_the_phone_numbers_are_exactly_the_published_ones(self):
        printed = {n for _, ns in C.PHONES for n in ns}
        self.assertEqual(len(printed), 12)
        html = page('Contact.html')
        for n in printed:
            self.assertIn(f'href="tel:{n}"', html)
        self.assertIn('mailto:jamiaululoom@gmail.com', html)


if __name__ == '__main__':
    unittest.main()
