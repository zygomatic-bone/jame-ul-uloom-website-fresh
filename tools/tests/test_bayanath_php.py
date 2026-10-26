"""Tests for jame-server/bayanath-update.php, the updater that runs on the website's own hosting from cron.

The real PHP script runs as a subprocess against the same LOCAL fake YouTube that tools/tests/test_update_bayanath.py uses.
They prove the logic (discovery, de-duplication, failure handling, the Saturday 21:00 India-time slot, locking). They do NOT
prove that a real YouTube upload is picked up: that is visible only in the log of the first real run on the hosting.
Skipped when PHP is not installed.
"""
import fcntl, json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import test_update_bayanath as T

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / 'jame-server'
PHP = shutil.which('php')
SAT_2105 = '2026-10-24T21:05:00+05:30'   # a Saturday


@unittest.skipUnless(PHP, 'PHP is not installed')
class PhpBase(T.Base):
    def setUp(self):
        super().setUp()
        self.data_dir = self.dir / 'data'
        self.conf = self.dir / 'config.php'
        self.write_config({})

    def write_config(self, extra):
        b = dict(T.CONFIG); b.update(extra)
        self.conf.write_text("<?php return ['data_dir' => %s, 'bayanath' => json_decode(%s, true)];\n" % (json.dumps(str(self.data_dir)).replace('$', '\\$'), "'" + json.dumps(b).replace("\\", "\\\\").replace("'", "\\'") + "'"))

    def run_php(self, args=('--force',), key=None, now=None, extra=None, tz=None):
        env = {'PATH': os.environ['PATH'], 'JAME_CONFIG': str(self.conf), 'BAYANATH_CACHE': str(self.cache),
               'YT_FEED_BASE': self.base + '/feed', 'YT_OEMBED_BASE': self.base + '/oembed', 'YT_CHANNEL_PAGE_BASE': self.base,
               'YT_API_BASE': self.base + '/api', 'YT_WATCH_BASE': self.base + '/watch'}
        if now:
            env['BAYANATH_NOW'] = now
        if tz:
            env['TZ'] = tz
        if key:
            env['YOUTUBE_API_KEY'] = key
        env.update(extra or {})
        return subprocess.run([PHP, str(SERVER / 'bayanath-update.php'), *args], env=env, capture_output=True, text=True, timeout=120)

    run_updater = run_php   # the shared helpers of the Python tests call this name

    def log(self):
        f = self.data_dir / 'logs' / 'bayanath.log'
        return f.read_text(encoding='utf-8') if f.exists() else ''


class Discovery(PhpBase):
    def test_new_eligible_video_is_added_and_unrelated_is_excluded(self):
        old = [T.entry(i, 20 - i) for i in range(1, 11)]
        self.seed(old)
        new, other = T.entry(11, 25), T.entry(12, 26, title='Cooking class: biryani at home')
        T.Fake.state['feed'] = [other, new] + old[:5]
        p = self.run_php()
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        ids = self.ids()
        self.assertEqual(ids[0], new['id'])
        self.assertNotIn(other['id'], ids)
        self.assertEqual(len(ids), 10)
        self.assertEqual(set(ids), {new['id']} | {e['id'] for e in old[:9]})   # the oldest fell out of the displayed ten; all others retained
        self.assertTrue(any(q.get('channel_id') == T.CHANNEL_ID for path, q, _ in T.Fake.seen if path == '/feed'), 'the configured channel id was queried')
        self.assertIn('new: 1', self.log())

    def test_existing_videos_are_retained_and_duplicates_never_added(self):
        e = [T.entry(1, 10), T.entry(2, 12), T.entry(3, 11)]
        self.seed(e)
        T.Fake.state['feed'] = [e[0], e[1], e[2], e[1], e[0]]
        self.assertEqual(self.run_php().returncode, 0)
        self.assertEqual(self.ids(), [e[1]['id'], e[2]['id'], e[0]['id']])
        self.assertEqual(len(set(self.ids())), len(self.ids()))

    def test_exactly_ten_when_more_available_and_fewer_when_not(self):
        T.Fake.state['feed'] = [T.entry(i, i) for i in range(1, 16)]
        self.assertEqual(self.run_php().returncode, 0)
        self.assertEqual(len(self.ids()), 10)
        self.assertEqual(self.ids()[0], T.vid(15))
        self.cache.unlink()
        T.Fake.state['feed'] = [T.entry(1, 3), T.entry(2, 4)]
        self.assertEqual(self.run_php().returncode, 0)
        self.assertEqual(len(self.ids()), 2)

    def test_unchanged_list_writes_nothing(self):
        T.Fake.state['feed'] = [T.entry(i, i) for i in range(1, 6)]
        self.assertEqual(self.run_php().returncode, 0)
        before, mtime = self.cache.read_bytes(), self.cache.stat().st_mtime_ns
        p = self.run_php()
        self.assertEqual(p.returncode, 0)
        self.assertEqual((before, mtime), (self.cache.read_bytes(), self.cache.stat().st_mtime_ns))
        self.assertIn('No change', p.stdout)

    def test_result_has_the_schema_the_website_and_the_python_checker_accept(self):
        T.Fake.state['feed'] = [T.entry(i, i) for i in range(1, 12)]
        self.assertEqual(self.run_php().returncode, 0)
        d = self.data()
        self.assertEqual(set(d), {'channel', 'updated', 'videos'})
        self.assertEqual(d['channel']['id'], T.CHANNEL_ID)
        for v in d['videos']:
            self.assertEqual(set(v), {'id', 'title', 'published', 'thumbnail'})
        sys.path.insert(0, str(ROOT / 'tools'))
        os.environ.setdefault('BAYANATH_CACHE', str(self.cache))
        import update_bayanath
        update_bayanath.validate(d, 10)   # the same validation the Python updater applies; raises if the PHP output differs
        self.assertEqual(oct(self.cache.stat().st_mode & 0o777), '0o644')
        self.assertEqual([p.name for p in self.dir.glob('by*') if p.is_file()], [], 'no temporary file left behind')

    def test_a_title_cut_off_with_an_ellipsis_is_repaired_and_a_date_is_never_invented(self):
        a, b = T.entry(1, 20), T.entry(2, 5)
        self.seed([a, {**b, 'title': 'Friday Bayan number 2 #jumma...', 'published': None}, {**T.entry(3, 3), 'published': None}])
        T.Fake.state['feed'] = [a]
        T.Fake.state['full_titles'] = {b['id']: 'Friday Bayan number 2 #jummabayan #full'}
        T.Fake.state['watch_dates'] = {b['id']: '2026-07-03'}
        self.assertEqual(self.run_php().returncode, 0)
        v = {x['id']: x for x in self.data()['videos']}
        self.assertEqual(v[b['id']]['title'], 'Friday Bayan number 2 #jummabayan #full')
        self.assertEqual(v[b['id']]['published'], '2026-07-03T00:00:00+00:00')
        self.assertIsNone(v[T.vid(3)]['published'])

    def test_deleted_video_is_dropped_and_an_oembed_outage_keeps_the_old_entries(self):
        e = [T.entry(i, i) for i in range(1, 5)]
        self.seed(e)
        T.Fake.state['feed'] = list(e)
        T.Fake.state['oembed'] = {e[3]['id']: 404}
        self.assertEqual(self.run_php().returncode, 0)
        self.assertNotIn(e[3]['id'], self.ids())
        T.Fake.state['oembed'] = {}; T.Fake.state['oembed_down'] = True
        before = self.cache.read_bytes()
        self.assertEqual(self.run_php().returncode, 0)
        self.assertEqual(before, self.cache.read_bytes())


class Failures(PhpBase):
    def test_source_failure_keeps_the_existing_list(self):
        self.seed([T.entry(i, i) for i in range(1, 6)])
        before = self.cache.read_bytes()
        T.Fake.state['feed_status'] = 500
        p = self.run_php()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(before, self.cache.read_bytes())
        self.assertIn('left untouched', self.log())

    def test_invalid_or_empty_answers_cannot_overwrite_the_list(self):
        self.seed([T.entry(i, i) for i in range(1, 6)])
        before = self.cache.read_bytes()
        for raw in ('<html>not xml', '<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
                    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><yt:videoId>bad id!</yt:videoId><title>Bayan</title><published>x</published></entry></feed>'):
            T.Fake.state['feed_raw'] = raw
            self.assertEqual(self.run_php().returncode, 1, raw)
            self.assertEqual(before, self.cache.read_bytes(), raw)

    def test_only_unrelated_videos_is_a_failure_not_an_empty_list(self):
        self.seed([T.entry(1, 1)])
        before = self.cache.read_bytes()
        T.Fake.state['feed'] = [T.entry(2, 5, title='Cricket highlights')]
        self.assertEqual(self.run_php().returncode, 1)
        self.assertEqual(before, self.cache.read_bytes())

    def test_wrong_channel_is_refused(self):
        self.seed([T.entry(1, 1)])
        before = self.cache.read_bytes()
        T.Fake.state['page_channel'] = 'UCzzzzzzzzzzzzzzzzzzzzzz'
        T.Fake.state['feed'] = [T.entry(2, 5)]
        self.assertEqual(self.run_php().returncode, 1)
        self.assertEqual(before, self.cache.read_bytes())

    def test_every_video_unavailable_is_a_failure_not_an_empty_list(self):
        e = [T.entry(i, i) for i in range(1, 4)]
        self.seed(e)
        before = self.cache.read_bytes()
        T.Fake.state['feed'] = list(e)
        T.Fake.state['oembed'] = {x['id']: 404 for x in e}
        self.assertEqual(self.run_php().returncode, 1)
        self.assertEqual(before, self.cache.read_bytes())

    def test_dry_run_changes_nothing(self):
        self.seed([T.entry(1, 1)])
        before = self.cache.read_bytes()
        T.Fake.state['feed'] = [T.entry(2, 5), T.entry(1, 1)]
        p = self.run_php(('--force', '--dry-run'))
        self.assertEqual(p.returncode, 0)
        self.assertIn('Dry run', p.stdout)
        self.assertEqual(before, self.cache.read_bytes())
        self.assertFalse((self.data_dir / 'bayanath-state.json').exists())

    def test_the_replaced_list_is_backed_up(self):
        self.seed([T.entry(1, 1)])
        T.Fake.state['feed'] = [T.entry(2, 5), T.entry(1, 1)]
        self.assertEqual(self.run_php().returncode, 0)
        backups = list((self.data_dir / 'bayanath-backup').glob('bayanath-videos-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual([v['id'] for v in json.loads(backups[0].read_text())['videos']], [T.vid(1)])


class Api(PhpBase):
    def test_api_key_goes_in_a_header_and_never_appears_anywhere(self):
        api = [T.entry(i, i) for i in range(1, 13)]
        api[0]['ok'] = False
        T.Fake.state['api'] = api
        p = self.run_php(key=T.SECRET)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertNotIn(T.SECRET, p.stdout + p.stderr + self.cache.read_text() + self.log())
        pl = [q for path, q, k in T.Fake.seen if path == '/api/playlistItems']
        self.assertEqual(pl[0]['playlistId'], 'UU' + T.CHANNEL_ID[2:])
        self.assertTrue(all(k == T.SECRET for path, q, k in T.Fake.seen if path.startswith('/api/')))
        self.assertFalse(any(T.SECRET in json.dumps(q) for path, q, k in T.Fake.seen))
        self.assertNotIn(T.vid(1), self.ids())
        self.assertEqual(len(self.ids()), 10)
        for f in self.data_dir.rglob('*'):
            if f.is_file():
                self.assertNotIn(T.SECRET, f.read_text(errors='replace'), str(f))

    def test_key_in_config_php_is_used_and_api_failure_falls_back_to_rss(self):
        self.conf.write_text(self.conf.read_text().replace("'bayanath' =>", "'youtube_api_key' => %r, 'bayanath' =>" % T.SECRET))
        T.Fake.state['api'] = []
        T.Fake.state['api_status'] = 403
        T.Fake.state['feed'] = [T.entry(1, 3)]
        p = self.run_php()
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertNotIn(T.SECRET, p.stdout + p.stderr + self.log())
        self.assertEqual(self.ids(), [T.vid(1)])
        self.assertIn('falling back', p.stdout)

    def test_an_upcoming_premiere_is_not_listed(self):
        up = T.entry(2, 9); up['live'] = 'upcoming'
        T.Fake.state['api'] = [T.entry(1, 3), up]
        self.assertEqual(self.run_php(key=T.SECRET).returncode, 0)
        self.assertEqual(self.ids(), [T.vid(1)])


class Safety(PhpBase):
    def test_a_redirect_off_the_trusted_hosts_is_refused_and_the_key_not_leaked(self):
        self.seed([T.entry(1, 3)])
        before = self.cache.read_text()
        T.Fake.state['api_status'] = 403   # the API step fails quietly, so the run falls back to the (redirecting) feed
        p = self.run_php(key=T.SECRET, extra={'YT_FEED_BASE': self.base + '/redirect-feed'})
        self.assertEqual(p.returncode, 1)
        self.assertIn('refusing a redirect', p.stdout)
        self.assertEqual(self.cache.read_text(), before)
        self.assertNotIn(T.SECRET, p.stdout + p.stderr + self.log())

    def test_only_https_youtube_hosts_or_the_local_test_server_may_be_contacted(self):
        self.seed([T.entry(1, 3)])
        before = self.cache.read_text()
        for bad in ('file:///etc/passwd', 'ftp://example.com/feed', 'https://example.com/feed', 'http://www.youtube.com/feeds/videos.xml', 'https://youtube.com.evil.example/feed'):
            p = self.run_php(extra={'YT_FEED_BASE': bad})
            self.assertEqual(p.returncode, 1, bad)
            self.assertIn('refusing to fetch', p.stdout, bad)
            self.assertEqual(self.cache.read_text(), before, bad)

    def test_it_cannot_be_started_from_the_web(self):
        import urllib.request, urllib.error, socket
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        proc = subprocess.Popen([PHP, '-S', f'127.0.0.1:{port}', '-t', str(SERVER)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(1)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/bayanath-update.php')
            self.assertEqual(cm.exception.code, 404)
        finally:
            proc.kill()
            proc.wait()

    def test_a_second_run_at_the_same_time_stops_at_the_lock(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.data_dir / 'bayanath.lock', 'w')
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            T.Fake.state['feed'] = [T.entry(1, 3)]
            p = self.run_php()
            self.assertEqual(p.returncode, 0)
            self.assertIn('already running', p.stdout)
            self.assertFalse(self.cache.exists())
            self.assertEqual([q for q in T.Fake.seen if q[0] == '/feed'], [])
        finally:
            fh.close()


class Schedule(PhpBase):
    """Saturday 21:00 Asia/Kolkata, decided by the script itself, so the server's own time zone does not matter."""
    def feed(self):
        T.Fake.state['feed'] = [T.entry(i, i) for i in range(1, 4)]

    def fetched(self):
        return len([q for q in T.Fake.seen if q[0] == '/feed'])

    def test_runs_once_at_the_first_tick_after_saturday_2100_ist_and_not_again_that_week(self):
        self.feed()
        p = self.run_php(now=SAT_2105, args=())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.fetched(), 1)
        self.assertIn('slot 2026-10-24T21:00:00+05:30', p.stdout)
        for later in ('2026-10-24T21:35:00+05:30', '2026-10-25T09:00:00+05:30', '2026-10-28T12:00:00+05:30', '2026-10-31T20:59:00+05:30'):
            self.assertEqual(self.run_php(now=later, args=()).returncode, 0)
        self.assertEqual(self.fetched(), 1, 'nothing more before next Saturday 21:00 IST')
        self.assertEqual(self.run_php(now='2026-10-31T21:00:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), 2, 'due again at the next Saturday 21:00 IST')

    def test_not_due_before_2100_on_saturday_for_a_fresh_install_it_still_catches_up_once(self):
        self.feed()
        # first ever run (no state): the most recent slot is last Saturday, so one catch-up run happens, then silence
        self.assertEqual(self.run_php(now='2026-10-24T20:59:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), 1)
        self.assertIn('slot 2026-10-17T21:00:00+05:30', self.log())
        self.assertEqual(self.run_php(now='2026-10-24T20:59:30+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), 1)

    def test_the_servers_own_time_zone_is_irrelevant(self):
        self.feed()
        # 21:05 IST is 15:35 UTC and 08:35 in Los Angeles: the same instant, the same decision
        for tz in ('UTC', 'America/Los_Angeles', 'Pacific/Auckland', 'Asia/Kolkata'):
            T.Fake.seen.clear(); self.cache.unlink(missing_ok=True)
            shutil.rmtree(self.data_dir, ignore_errors=True)
            p = self.run_php(now='2026-10-24T15:35:00Z', args=(), tz=tz)
            self.assertEqual(p.returncode, 0, tz + p.stderr)
            self.assertIn('slot 2026-10-24T21:00:00+05:30', p.stdout, tz)
            # one minute earlier (20:59 IST) belongs to the previous week's slot
            shutil.rmtree(self.data_dir, ignore_errors=True)
            p = self.run_php(now='2026-10-24T15:29:00Z', args=(), tz=tz)
            self.assertIn('slot 2026-10-17T21:00:00+05:30', p.stdout, tz)

    def test_missed_week_is_caught_up_at_the_next_tick(self):
        self.feed()
        self.assertEqual(self.run_php(now='2026-10-17T21:10:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), 1)
        # the server was off all of the next Saturday; it is back on Monday
        self.assertEqual(self.run_php(now='2026-10-26T10:00:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), 2)
        self.assertIn('slot 2026-10-24T21:00:00+05:30', self.log())

    def test_a_failed_run_is_retried_at_later_ticks_up_to_six_times_then_waits_for_next_week(self):
        self.seed([T.entry(1, 1)])
        T.Fake.state['feed_status'] = 500
        codes = [self.run_php(now=f'2026-10-24T21:{5 + 5 * i:02d}:00+05:30', args=()).returncode for i in range(8)]
        self.assertEqual(codes, [1, 1, 1, 1, 1, 1, 0, 0])   # attempts 7 and 8 are not made
        self.assertEqual(self.fetched(), 6)
        T.Fake.state['feed_status'] = 200
        T.Fake.state['feed'] = [T.entry(2, 4), T.entry(1, 1)]
        self.assertEqual(self.run_php(now='2026-10-31T21:05:00+05:30', args=()).returncode, 0)   # next week starts fresh
        self.assertEqual(self.ids()[0], T.vid(2))

    def test_a_retry_that_succeeds_ends_the_weeks_attempts(self):
        self.seed([T.entry(1, 1)])
        T.Fake.state['feed_status'] = 500
        self.assertEqual(self.run_php(now='2026-10-24T21:05:00+05:30', args=()).returncode, 1)
        T.Fake.state['feed_status'] = 200
        T.Fake.state['feed'] = [T.entry(2, 4), T.entry(1, 1)]
        self.assertEqual(self.run_php(now='2026-10-24T21:35:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.ids()[0], T.vid(2))
        n = self.fetched()
        self.assertEqual(self.run_php(now='2026-10-24T22:05:00+05:30', args=()).returncode, 0)
        self.assertEqual(self.fetched(), n)

    def test_the_cron_instructions_in_the_readme_and_config_agree_with_the_slot(self):
        text = (ROOT / 'jame-server' / 'bayanath-update.php').read_text(encoding='utf-8')
        self.assertIn("'timezone' => 'Asia/Kolkata', 'weekday' => 6, 'hour' => 21, 'minute' => 0", text)


class ProductionLayout(PhpBase):
    def test_it_finds_public_html_next_to_jame_server_and_needs_no_environment_hints(self):
        site = self.dir / 'account'
        shutil.copytree(SERVER, site / 'jame-server', ignore=shutil.ignore_patterns('data', 'config.php'))
        (site / 'public_html' / 'data').mkdir(parents=True)
        (site / 'jame-server' / 'config.php').write_text("<?php return ['bayanath' => ['title_keywords' => ['bayan']]];\n")
        T.Fake.state['feed'] = [T.entry(1, 3), T.entry(2, 4)]
        env = {'PATH': os.environ['PATH'], 'YT_FEED_BASE': self.base + '/feed', 'YT_OEMBED_BASE': self.base + '/oembed', 'YT_CHANNEL_PAGE_BASE': self.base,
               'BAYANATH_NOW': SAT_2105}
        p = subprocess.run([PHP, str(site / 'jame-server' / 'bayanath-update.php')], env=env, capture_output=True, text=True, cwd='/', timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = json.loads((site / 'public_html' / 'data' / 'bayanath-videos.json').read_text())
        self.assertEqual([v['id'] for v in out['videos']], [T.vid(2), T.vid(1)])
        self.assertTrue((site / 'jame-server' / 'data' / 'logs' / 'bayanath.log').exists())


if __name__ == '__main__':
    unittest.main()
