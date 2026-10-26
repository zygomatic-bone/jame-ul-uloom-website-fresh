"""Tests of the website form handler (public/api/submit.php + jame-server/forms.php) with the real PHP interpreter.

A throw-away PHP server is started on a free local port with a temporary configuration (mail driver "file", so nothing is sent).
The tests are skipped when PHP is not installed.

Run:  python3 -I -m unittest discover -s tools/tests -v
"""
import json, os, shutil, socket, subprocess, tempfile, time, unittest
from pathlib import Path
from urllib import request, parse, error

ROOT = Path(__file__).resolve().parents[2]
PHP = shutil.which('php')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


GOOD = {
    'feedback': {'form': 'feedback', 'rating': '5', 'category': 'appreciation', 'message': 'Thank you for the care shown to my son.', 'audience': 'parent', 'name': 'Test Parent', 'email': 'parent@example.org', 'opened': '9000'},
    'admissions': {'form': 'admissions', 'guardian': 'Test Guardian', 'phone': '+91 98765 43210', 'programme': 'pu', 'level': 'First year', 'consent': 'on', 'opened': '9000'},
    'careers': {'form': 'careers', 'name': 'Test Candidate', 'phone': '9876543210', 'email': 'candidate@example.org', 'area': 'teaching-school', 'consent': 'on', 'opened': '9000'},
}


@unittest.skipUnless(PHP, 'PHP is not installed')
class Forms(unittest.TestCase):
    cfg_extra = ''

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.port = free_port()
        self.write_config()
        env = dict(os.environ, JAME_CONFIG=str(self.tmp / 'config.php'), JAME_SERVER_DIR=str(ROOT / 'jame-server'))
        self.proc = subprocess.Popen([PHP, '-S', f'127.0.0.1:{self.port}', '-t', str(ROOT / 'public')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, **over):
        cfg = {'mail_to': "['office@example.org']", 'mail_from': "'website@example.org'", 'mail_driver': "'file'", 'allowed_hosts': "['127.0.0.1']",
               'salt': "'test'", 'data_dir': f"'{self.tmp}/data'", 'rate': "['per_ip_hour' => 50, 'per_ip_day' => 150, 'global_day' => 500]", 'min_fill_seconds': '2'}
        cfg.update(over)
        (self.tmp / 'config.php').write_text('<?php return [' + ', '.join(f"'{k}' => {v}" for k, v in cfg.items()) + '];')

    def post(self, data, origin='http://127.0.0.1', json_reply=True, method='POST', raw=None):
        body = raw if raw is not None else parse.urlencode(data or {}).encode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if origin:
            headers['Origin'] = origin
        if json_reply:
            headers['Accept'] = 'application/json'
        req = request.Request(f'http://127.0.0.1:{self.port}/api/submit.php', data=None if method == 'GET' else body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def outbox(self):
        d = self.tmp / 'data' / 'outbox'
        return sorted(d.glob('*.eml')) if d.exists() else []

    def test_each_form_is_accepted_mailed_and_stored(self):
        for form, data in GOOD.items():
            status, body, h = self.post(data)
            self.assertEqual(status, 200, body)
            j = json.loads(body)
            self.assertTrue(j['ok'])
            self.assertRegex(j['ref'], r'^JU-[A-Z]{2}-[A-Z2-9]{6}$')
            self.assertEqual(h['Cache-Control'], 'no-store')
        mails = [m.read_text() for m in self.outbox()]
        self.assertEqual(len(mails), 3)
        self.assertTrue(any('Subject: [Jame ul uloom website] Feedback: 5 of 5, Appreciation' in m and 'Reply-To: parent@example.org' in m for m in mails))
        self.assertTrue(any('Admissions enquiry: Pre University College for Girls' in m for m in mails))
        store = next((self.tmp / 'data' / 'submissions').glob('*.jsonl')).read_text().splitlines()
        self.assertEqual(len(store), 3)
        self.assertTrue(all(json.loads(l)['mailed'] for l in store))

    def test_invalid_input_is_refused_field_by_field(self):
        bad = dict(GOOD['feedback'], rating='9', category='nonsense', message='hi', email='not-an-email')
        status, body, _ = self.post(bad)
        self.assertEqual(status, 422)
        self.assertEqual(set(json.loads(body)['errors']), {'rating', 'category', 'message', 'email'})
        self.assertEqual(self.outbox(), [])
        status, body, _ = self.post({k: v for k, v in GOOD['admissions'].items() if k != 'consent'})
        self.assertEqual(status, 422)
        self.assertIn('consent', json.loads(body)['errors'])
        status, body, _ = self.post(dict(GOOD['careers'], phone='abc'))
        self.assertEqual(status, 422)
        status, body, _ = self.post(dict(GOOD['feedback'], message='x' * 2001))
        self.assertEqual(status, 422)
        listy = {k: v for k, v in GOOD['feedback'].items() if k != 'name'}
        listy['name[]'] = 'x'   # a list where text is expected
        status, body, _ = self.post(listy)
        self.assertEqual(status, 422)
        self.assertIn('name', json.loads(body)['errors'])

    def test_header_injection_is_impossible(self):
        evil = 'a@example.org\r\nBcc: victim@example.org'
        status, body, _ = self.post(dict(GOOD['feedback'], email=evil))
        self.assertEqual(status, 422)
        status, body, _ = self.post(dict(GOOD['feedback'], name='Eve\r\nBcc: victim@example.org', message='Line one\r\nBcc: victim@example.org is just text'))
        self.assertEqual(status, 200)
        mail = self.outbox()[-1].read_bytes().decode()
        head = mail.split('\r\n\r\n', 1)[0]
        self.assertIn('Reply-To: parent@example.org', head)
        self.assertEqual(len(head.splitlines()), 8)   # To, Subject, From, MIME-Version, Content-Type, Content-Transfer-Encoding, X-Mailer, Reply-To
        self.assertNotIn('victim@example.org', head)   # nothing from the visitor reached a header except the checked Reply-To

    def test_only_our_own_site_may_post(self):
        for origin in (None, 'http://evil.example', 'http://127.0.0.1.evil.example'):
            status, body, _ = self.post(GOOD['feedback'], origin=origin)
            self.assertEqual(status, 403, origin)
        status, _, h = self.post(None, method='GET')
        self.assertEqual(status, 405)
        self.assertEqual(h.get('Allow'), 'POST')
        self.assertEqual(self.outbox(), [])

    def test_robots_are_refused(self):
        status, _, _ = self.post(dict(GOOD['feedback'], website='http://spam.example'))
        self.assertEqual(status, 400)
        status, _, _ = self.post(dict(GOOD['feedback'], opened='300'))
        self.assertEqual(status, 400)
        status, _, _ = self.post(dict(GOOD['feedback'], form='nothing'))
        self.assertEqual(status, 400)
        self.assertEqual(self.outbox(), [])

    def test_rate_limit(self):
        self.write_config(rate="['per_ip_hour' => 2, 'per_ip_day' => 5, 'global_day' => 500]")
        codes = [self.post(GOOD['feedback'])[0] for _ in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])
        self.assertEqual(len(self.outbox()), 2)

    def test_too_large_a_body_is_refused(self):
        status, _, _ = self.post(None, raw=b'form=feedback&message=' + b'a' * 30000)
        self.assertEqual(status, 413)

    def test_failure_to_deliver_is_never_reported_as_success(self):
        (self.tmp / 'data').mkdir(parents=True, exist_ok=True)
        (self.tmp / 'data' / 'outbox').write_text('a file where the mail folder should be')
        status, body, _ = self.post(GOOD['feedback'])
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)['ok'])
        store = next((self.tmp / 'data' / 'submissions').glob('*.jsonl')).read_text()   # the copy is kept for the office
        self.assertFalse(json.loads(store.splitlines()[0])['mailed'])

    def test_missing_configuration_is_reported_honestly(self):
        (self.tmp / 'config.php').unlink()
        status, body, _ = self.post(GOOD['feedback'])
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)['ok'])

    def test_urdu_text_and_markup_are_kept_as_plain_text_and_never_echoed(self):
        payload = 'شکریہ <script>alert(1)</script> & "quotes"'
        status, body, _ = self.post(dict(GOOD['feedback'], message=payload), json_reply=False)
        self.assertEqual(status, 200)
        self.assertNotIn('<script>', body)
        self.assertNotIn('شکریہ', body)
        self.assertIn(payload, self.outbox()[0].read_text(encoding='utf-8'))
        status, body, _ = self.post(dict(GOOD['feedback'], rating='0'), json_reply=False)
        self.assertEqual(status, 422)
        self.assertIn('<h1>We could not send this</h1>', body)


if __name__ == '__main__':
    unittest.main()
