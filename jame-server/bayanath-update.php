<?php
/* Bayanath updater: keeps public_html/data/bayanath-videos.json current from the official YouTube channel.
   Runs on the website's own hosting from a cron job; no GitHub, Netlify or browser is involved.

   Usage (command line only):
       php bayanath-update.php            run if the weekly slot is due (Saturday 21:00 India time), otherwise do nothing
       php bayanath-update.php --force    run now, whatever the time
       php bayanath-update.php --dry-run  do everything except write the file (add --force to ignore the slot)

   Schedule: put ONE cron job that starts this file every 30 minutes (see README, "Weekly Bayanath updates").
   The script itself decides when it is Saturday 21:00 in Asia/Kolkata, so the server's own time zone does not matter.
   Per week the update runs once: at the first cron tick at or after Saturday 21:00 IST. If that run fails it is retried on the
   next ticks (up to 6 attempts); if the server was down, the next tick after it comes back catches up.

   Safety: the published file is replaced only by a complete, validated, newer-or-equal list, written to a temporary file and
   renamed into place (visitors never see a half-written file). Any failure (network, bad XML/JSON, zero videos, wrong
   channel, invalid result) leaves the existing file untouched. A copy of every list that is replaced is kept in
   data/bayanath-backup/ (last 8). Only one run at a time (flock). Only https addresses on YouTube/Google are contacted.
   An optional YouTube Data API key is read from config.php (or the YOUTUBE_API_KEY environment variable), sent in a request
   header, and never printed or logged.

   Test hooks (environment): JAME_CONFIG, BAYANATH_CACHE, BAYANATH_NOW (a fake clock), YT_FEED_BASE, YT_OEMBED_BASE,
   YT_CHANNEL_PAGE_BASE, YT_API_BASE, YT_WATCH_BASE. They only matter to whoever can already run commands on the account.
   Compatible with PHP 7.4 and later; needs the curl extension or allow_url_fopen, and SimpleXML. */

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

const BY_ID_RE = '/^[A-Za-z0-9_-]{11}$/';
const BY_TRUSTED = ['youtube.com', 'google.com', 'googleapis.com', 'ytimg.com'];
const BY_LOOPBACK = ['127.0.0.1', 'localhost', '::1'];
const BY_MAX_BYTES = 5000000;
const BY_MAX_ATTEMPTS = 6;
const BY_UA = 'Mozilla/5.0 (compatible; JameUlUloomBayanathBot/3.0; +https://jameululoom.org)';

$GLOBALS['by_log_file'] = null;
$GLOBALS['by_key'] = '';

function by_log(string $msg): void {
    $line = gmdate('Y-m-d\TH:i:s\Z') . ' ' . $msg;
    echo $line . "\n";
    $f = $GLOBALS['by_log_file'];
    if ($f) {
        if (is_file($f) && filesize($f) > 524288) {
            @rename($f, $f . '.1');
        }
        @file_put_contents($f, $line . "\n", FILE_APPEND | LOCK_EX);
    }
}

function by_fail(string $msg): void {
    $msg = by_scrub($msg);
    by_log('ERROR: ' . $msg);
    by_log('The published list was left untouched.');
    exit(1);
}

/* never let the API key reach the log or the screen, whatever a library puts into a message */
function by_scrub(string $s): string {
    $k = $GLOBALS['by_key'];
    return $k !== '' ? str_replace($k, '[key]', $s) : $s;
}

function by_lc(string $s): string {
    return function_exists('mb_strtolower') ? mb_strtolower($s, 'UTF-8') : strtolower($s);
}

function by_allowed(string $url): bool {
    $p = parse_url($url);
    if (!is_array($p) || empty($p['host']) || empty($p['scheme'])) {
        return false;
    }
    $host = strtolower(trim($p['host'], '[]'));
    if (in_array($host, BY_LOOPBACK, true)) {
        return in_array($p['scheme'], ['http', 'https'], true);
    }
    if ($p['scheme'] !== 'https') {
        return false;
    }
    foreach (BY_TRUSTED as $d) {
        if ($host === $d || substr($host, -strlen('.' . $d)) === '.' . $d) {
            return true;
        }
    }
    return false;
}

function by_host(string $url): string {
    $p = parse_url($url);
    return strtolower((string) ($p['host'] ?? ''));
}

/* One request without following redirects. Returns [status, headers (lower-case names), body]; throws on transport errors. */
function by_once(string $url, array $headers, int $timeout): array {
    $h = ['User-Agent: ' . BY_UA, 'Accept-Language: en', 'Cookie: CONSENT=YES+1'];
    foreach ($headers as $k => $v) {
        $h[] = $k . ': ' . $v;
    }
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        $body = '';
        $rh = [];
        curl_setopt_array($ch, [
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_TIMEOUT => $timeout, CURLOPT_CONNECTTIMEOUT => 10, CURLOPT_HTTPHEADER => $h,
            CURLOPT_PROTOCOLS => (defined('CURLPROTO_HTTPS') ? CURLPROTO_HTTPS | CURLPROTO_HTTP : 3),
            CURLOPT_HEADERFUNCTION => function ($c, $line) use (&$rh) {
                $p = explode(':', $line, 2);
                if (count($p) === 2) {
                    $rh[strtolower(trim($p[0]))] = trim($p[1]);
                }
                return strlen($line);
            },
            CURLOPT_WRITEFUNCTION => function ($c, $chunk) use (&$body) {
                $body .= $chunk;
                return strlen($body) > BY_MAX_BYTES ? 0 : strlen($chunk);
            },
        ]);
        $ok = curl_exec($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $err = curl_error($ch);
        curl_close($ch);
        if ($ok === false) {
            throw new RuntimeException('request failed: ' . $err);
        }
        return [$status, $rh, $body];
    }
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => implode("\r\n", $h), 'timeout' => $timeout, 'follow_location' => 0, 'ignore_errors' => true]]);
    $body = @file_get_contents($url, false, $ctx, 0, BY_MAX_BYTES);
    if ($body === false || empty($http_response_header)) {
        throw new RuntimeException('request failed');
    }
    $status = 0;
    $rh = [];
    foreach ($http_response_header as $i => $line) {
        if ($i === 0 && preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $m)) {
            $status = (int) $m[1];
        } elseif (strpos($line, ':') !== false) {
            [$k, $v] = explode(':', $line, 2);
            $rh[strtolower(trim($k))] = trim($v);
        }
    }
    return [$status, $rh, $body];
}

/* Redirects are followed by hand, only to trusted hosts, and the API key header never leaves the host it was meant for. */
function by_get(string $url, array $headers = [], int $timeout = 25): array {
    for ($hops = 0; $hops < 4; $hops++) {
        if (!by_allowed($url)) {
            throw new RuntimeException('refusing to fetch ' . (parse_url($url, PHP_URL_SCHEME) ?: '?') . '://' . (by_host($url) ?: '?'));
        }
        [$status, $rh, $body] = by_once($url, $headers, $timeout);
        if (in_array($status, [301, 302, 303, 307, 308], true) && !empty($rh['location'])) {
            $next = $rh['location'];
            if (!preg_match('#^[a-z][a-z0-9+.-]*://#i', $next)) {
                $u = parse_url($url);
                $next = $u['scheme'] . '://' . $u['host'] . (isset($u['port']) ? ':' . $u['port'] : '') . ($next[0] === '/' ? $next : '/' . $next);
            }
            if (!by_allowed($next)) {
                throw new RuntimeException('refusing a redirect to ' . (by_host($next) ?: '?'));
            }
            if (by_host($next) !== by_host($url)) {
                unset($headers['X-Goog-Api-Key']);
            }
            $url = $next;
            continue;
        }
        return [$status, $body];
    }
    throw new RuntimeException('too many redirects');
}

function by_valid_iso($s): bool {
    if (!is_string($s) || !preg_match('/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/', $s)) {
        return false;
    }
    try {
        new DateTimeImmutable($s);
        return true;
    } catch (Exception $e) {
        return false;
    }
}

function by_ts($s): int {
    if (!$s) {
        return PHP_INT_MIN;
    }
    return (new DateTimeImmutable($s, new DateTimeZone('UTC')))->getTimestamp();
}

/* ---- the weekly slot ---------------------------------------------------------------------------------------------- */
function by_last_slot(DateTimeImmutable $now, array $s): DateTimeImmutable {
    $d = $now->setTime((int) $s['hour'], (int) $s['minute'], 0);
    $guard = 0;
    while (($d > $now || (int) $d->format('N') !== (int) $s['weekday']) && $guard++ < 15) {
        $d = $d->modify('-1 day')->setTime((int) $s['hour'], (int) $s['minute'], 0);
    }
    return $d;
}

/* ---- discovery ---------------------------------------------------------------------------------------------------- */
function by_feed(array $cfg, string $base): array {
    $q = !empty($cfg['playlist_id']) ? ['playlist_id' => $cfg['playlist_id']] : ['channel_id' => $cfg['channel_id']];
    $url = $base . '?' . http_build_query($q);
    try {
        [$status, $body] = by_get($url);
    } catch (Exception $e) {
        by_fail('could not download the YouTube feed: ' . $e->getMessage());
    }
    if ($status !== 200) {
        by_fail('the YouTube feed answered with HTTP ' . $status);
    }
    $prev = libxml_use_internal_errors(true);
    $xml = simplexml_load_string($body, 'SimpleXMLElement', LIBXML_NONET | LIBXML_NOCDATA);
    libxml_use_internal_errors($prev);
    if ($xml === false) {
        by_fail('the YouTube feed is not valid XML');
    }
    $out = [];
    foreach ($xml->entry as $e) {
        $yt = $e->children('http://www.youtube.com/xml/schemas/2015');
        $vid = trim((string) $yt->videoId);
        $title = trim((string) $e->title);
        $pub = trim((string) $e->published);
        if (!preg_match(BY_ID_RE, $vid) || $title === '' || !by_valid_iso($pub)) {
            continue;
        }
        $thumb = '';
        $media = $e->children('http://search.yahoo.com/mrss/');
        if (isset($media->group)) {
            $t = $media->group->children('http://search.yahoo.com/mrss/')->thumbnail;
            if (isset($t['url'])) {
                $thumb = (string) $t['url'];
            }
        }
        $out[] = ['id' => $vid, 'title' => $title, 'published' => $pub, 'thumbnail' => $thumb !== '' ? $thumb : 'https://i.ytimg.com/vi/' . $vid . '/hqdefault.jpg'];
    }
    return $out;
}

function by_api(string $base, string $path, array $params): array {
    [$status, $body] = by_get($base . '/' . $path . '?' . http_build_query($params), ['X-Goog-Api-Key' => $GLOBALS['by_key'], 'Accept' => 'application/json']);
    if ($status !== 200) {
        throw new RuntimeException('HTTP ' . $status);
    }
    $j = json_decode($body, true);
    if (!is_array($j)) {
        throw new RuntimeException('not JSON');
    }
    return $j;
}

/* Returns [videos, unavailable ids]. */
function by_fetch_api(array $cfg, string $base): array {
    $pid = !empty($cfg['playlist_id']) ? $cfg['playlist_id'] : 'UU' . substr($cfg['channel_id'], 2);
    $ids = [];
    $token = null;
    while (count($ids) < 50) {
        $params = ['part' => 'contentDetails', 'playlistId' => $pid, 'maxResults' => 50];
        if ($token) {
            $params['pageToken'] = $token;
        }
        $page = by_api($base, 'playlistItems', $params);
        foreach (($page['items'] ?? []) as $i) {
            $v = $i['contentDetails']['videoId'] ?? '';
            if (is_string($v) && preg_match(BY_ID_RE, $v)) {
                $ids[] = $v;
            }
        }
        $token = $page['nextPageToken'] ?? null;
        if (!$token) {
            break;
        }
    }
    $ids = array_slice(array_values(array_unique($ids)), 0, 50);
    if (!$ids) {
        throw new RuntimeException('the uploads playlist returned no videos');
    }
    $data = by_api($base, 'videos', ['part' => 'snippet,status', 'id' => implode(',', $ids), 'maxResults' => 50]);
    $out = [];
    $seen = [];
    foreach (($data['items'] ?? []) as $it) {
        $vid = (string) ($it['id'] ?? '');
        $sn = $it['snippet'] ?? [];
        $st = $it['status'] ?? [];
        $seen[] = $vid;
        $pub = (string) ($sn['publishedAt'] ?? '');
        if (!preg_match(BY_ID_RE, $vid) || empty($sn['title']) || !by_valid_iso($pub)) {
            continue;
        }
        if (($st['privacyStatus'] ?? '') !== 'public' || (($st['embeddable'] ?? true) === false) || ($sn['liveBroadcastContent'] ?? '') === 'upcoming') {
            continue;
        }
        $out[] = ['id' => $vid, 'title' => trim((string) $sn['title']), 'published' => $pub, 'thumbnail' => 'https://i.ytimg.com/vi/' . $vid . '/hqdefault.jpg'];
    }
    return [$out, array_values(array_diff($ids, $seen))];
}

function by_eligible(array $v, array $cfg): bool {
    $t = by_lc($v['title']);
    foreach (($cfg['exclude_keywords'] ?? []) as $k) {
        if ($k !== '' && strpos($t, by_lc($k)) !== false) {
            return false;
        }
    }
    if (!empty($cfg['playlist_id'])) {
        return true;
    }
    $kws = array_values(array_filter($cfg['title_keywords'] ?? [], function ($k) { return $k !== ''; }));
    if (!$kws) {
        return true;
    }
    foreach ($kws as $k) {
        if (strpos($t, by_lc($k)) !== false) {
            return true;
        }
    }
    return false;
}

/* [available (true / false / null = could not tell), title] */
function by_oembed(string $base, string $id): array {
    $url = $base . '?' . http_build_query(['url' => 'https://www.youtube.com/watch?v=' . $id, 'format' => 'json']);
    try {
        [$status, $body] = by_get($url, [], 15);
    } catch (Exception $e) {
        return [null, null];
    }
    if ($status === 200) {
        $j = json_decode($body, true);
        return [true, is_array($j) ? trim((string) ($j['title'] ?? '')) : ''];
    }
    return [in_array($status, [400, 401, 403, 404], true) ? false : null, null];
}

function by_truncated(string $t): bool {
    $t = rtrim($t);
    return substr($t, -3) === '...' || substr($t, -3) === '…';
}

function by_repair_title(string $old, ?string $full): string {
    if (!$full || !by_truncated($old)) {
        return $old;
    }
    $stem = preg_replace('/[.…\s]+$/u', '', $old);
    return (strpos($full, $stem) === 0 && strlen($full) >= strlen($stem)) ? $full : $old;
}

function by_watch_date(string $base, string $id): ?string {
    try {
        [$status, $body] = by_get($base . '?' . http_build_query(['v' => $id]), [], 15);
    } catch (Exception $e) {
        return null;
    }
    $body = substr($body, 0, 600000);
    if (!preg_match('/itemprop="uploadDate"\s+content="([^"]+)"/', $body, $m) && !preg_match('/itemprop="datePublished"\s+content="([^"]+)"/', $body, $m) && !preg_match('/"publishDate":"([^"]+)"/', $body, $m)) {
        return null;
    }
    if (!by_valid_iso($m[1])) {
        return null;
    }
    $d = new DateTimeImmutable($m[1], new DateTimeZone('UTC'));   // a bare date has no time: keep it as a date at UTC midnight
    return $d->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s') . '+00:00';
}

/* Throws unless the structure is exactly what the website renders (same rules as tools/update_bayanath.py). */
function by_validate(array $data, int $limit): void {
    $vids = $data['videos'] ?? null;
    if (!is_array($vids) || !$vids) {
        throw new RuntimeException('no videos');
    }
    if (count($vids) > $limit) {
        throw new RuntimeException('more than ' . $limit . ' videos');
    }
    $ids = array_map(function ($v) { return $v['id'] ?? null; }, $vids);
    if (count(array_unique($ids)) !== count($ids)) {
        throw new RuntimeException('duplicate video ids');
    }
    $last = null;
    foreach ($vids as $v) {
        $id = $v['id'] ?? '';
        if (!is_string($id) || !preg_match(BY_ID_RE, $id)) {
            throw new RuntimeException('bad video id');
        }
        if (!isset($v['title']) || !is_string($v['title']) || trim($v['title']) === '') {
            throw new RuntimeException($id . ': empty title');
        }
        if (($v['published'] ?? null) !== null && !by_valid_iso($v['published'])) {
            throw new RuntimeException($id . ': bad date');
        }
        if (!preg_match('#^https://(?:i\d?\.ytimg\.com|img\.youtube\.com)/vi/' . preg_quote($id, '#') . '/[^?\#]+(?:[?\#].*)?$#', (string) ($v['thumbnail'] ?? ''))) {
            throw new RuntimeException($id . ': thumbnail is not derived from the video id');
        }
        $cur = by_ts($v['published'] ?? null);
        if ($last !== null && $cur > $last) {
            throw new RuntimeException('not sorted newest first');
        }
        $last = $cur;
    }
}

function by_json(array $data): string {
    return json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n";
}

/* temp file in the same folder, then rename: the published file is always complete */
function by_write_atomic(string $path, string $content): void {
    $dir = dirname($path);
    if (!is_dir($dir) && !@mkdir($dir, 0755, true)) {
        throw new RuntimeException('cannot create ' . $dir);
    }
    $tmp = @tempnam($dir, 'by');
    if ($tmp === false) {
        throw new RuntimeException('cannot write in ' . $dir . ' (check the folder permissions)');
    }
    if (file_put_contents($tmp, $content) !== strlen($content)) {
        @unlink($tmp);
        throw new RuntimeException('could not write the temporary file');
    }
    @chmod($tmp, 0644);
    if (!@rename($tmp, $path)) {
        @unlink($tmp);
        throw new RuntimeException('could not move the new list into place');
    }
}

function by_backup(string $cache, string $dir): void {
    if (!is_file($cache)) {
        return;
    }
    if (!is_dir($dir)) {
        @mkdir($dir, 0700, true);
    }
    @copy($cache, $dir . '/bayanath-videos-' . gmdate('Ymd-His') . '.json');
    $all = glob($dir . '/bayanath-videos-*.json') ?: [];
    sort($all);
    foreach (array_slice($all, 0, max(0, count($all) - 8)) as $old) {
        @unlink($old);
    }
}

function by_state_read(string $f): array {
    $j = is_file($f) ? json_decode((string) @file_get_contents($f), true) : null;
    return is_array($j) ? $j : [];
}

function by_state_write(string $f, array $s): void {
    @file_put_contents($f, json_encode($s, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n", LOCK_EX);
}

/* ---- main --------------------------------------------------------------------------------------------------------- */
function by_main(array $argv): void {
    $force = in_array('--force', $argv, true);
    $dry = in_array('--dry-run', $argv, true);
    $cfgFile = getenv('JAME_CONFIG') ?: __DIR__ . '/config.php';
    $site = is_file($cfgFile) ? (include $cfgFile) : [];
    $site = is_array($site) ? $site : [];
    $dataDir = $site['data_dir'] ?? __DIR__ . '/data';
    $b = ($site['bayanath'] ?? []) + [
        'channel_handle' => 'MuftiMaqsoodImran', 'channel_id' => 'UClF-O3ig9ZKMvbeKB4t9mjQ', 'playlist_id' => '',
        'title_keywords' => ['bayan', 'bayanat', 'bayanath', 'بیان', 'بیانات', 'بيان'], 'exclude_keywords' => [], 'max_videos' => 10,
        'timezone' => 'Asia/Kolkata', 'weekday' => 6, 'hour' => 21, 'minute' => 0,
        'cache' => dirname(__DIR__) . '/public_html/data/bayanath-videos.json',
    ];
    $cache = getenv('BAYANATH_CACHE') ?: $b['cache'];
    $limit = max(1, (int) $b['max_videos']);
    $GLOBALS['by_key'] = trim((string) (getenv('YOUTUBE_API_KEY') ?: ($site['youtube_api_key'] ?? '')));
    if (!is_dir($dataDir . '/logs') && !@mkdir($dataDir . '/logs', 0700, true)) {
        fwrite(STDERR, "ERROR: cannot create {$dataDir}/logs (set 'data_dir' in config.php to a writable folder)\n");
        exit(1);
    }
    $GLOBALS['by_log_file'] = $dataDir . '/logs/bayanath.log';

    $lock = fopen($dataDir . '/bayanath.lock', 'c');
    if (!$lock || !flock($lock, LOCK_EX | LOCK_NB)) {
        by_log('Another update is already running; this one stops without doing anything.');
        exit(0);
    }

    /* --- is it time? --- */
    try {
        $tz = new DateTimeZone((string) $b['timezone']);
        $now = (new DateTimeImmutable(getenv('BAYANATH_NOW') ?: 'now'))->setTimezone($tz);   /* always judged in India time, whatever the server's own zone is */
    } catch (Exception $e) {
        by_fail('invalid time zone or test clock: ' . $e->getMessage());
    }
    $slot = by_last_slot($now, $b);
    $slotKey = $slot->format('c');
    $stateFile = $dataDir . '/bayanath-state.json';
    $state = by_state_read($stateFile);
    if (!$force) {
        if (($state['ok_slot'] ?? '') === $slotKey) {
            exit(0);   /* this week's update is done: nothing to say, nothing to log */
        }
        if (($state['slot'] ?? '') === $slotKey && (int) ($state['attempts'] ?? 0) >= BY_MAX_ATTEMPTS) {
            exit(0);   /* gave up for this week; the next Saturday slot starts fresh (or run with --force) */
        }
    }
    if (($state['slot'] ?? '') !== $slotKey) {
        $state['slot'] = $slotKey;   /* a new week: start counting attempts again */
        $state['attempts'] = 0;
    }
    $state['attempts'] = (int) ($state['attempts'] ?? 0) + 1;
    $state['last_attempt'] = $now->format('c');
    by_log('Update starting (slot ' . $slotKey . ', attempt ' . $state['attempts'] . ($force ? ', forced' : '') . ($dry ? ', dry run' : '') . ')');
    if (!$dry) {
        by_state_write($stateFile, $state);
    }

    $feedBase = getenv('YT_FEED_BASE') ?: 'https://www.youtube.com/feeds/videos.xml';
    $oembedBase = getenv('YT_OEMBED_BASE') ?: 'https://www.youtube.com/oembed';
    $pageBase = getenv('YT_CHANNEL_PAGE_BASE') ?: 'https://www.youtube.com';
    $apiBase = getenv('YT_API_BASE') ?: 'https://www.googleapis.com/youtube/v3';
    $watchBase = getenv('YT_WATCH_BASE') ?: 'https://www.youtube.com/watch';

    $cacheData = is_file($cache) ? json_decode((string) file_get_contents($cache), true) : null;
    $old = [];
    foreach ((is_array($cacheData) ? ($cacheData['videos'] ?? []) : []) as $v) {
        if (is_array($v) && isset($v['id']) && preg_match(BY_ID_RE, (string) $v['id'])) {
            $old[] = $v;
        }
    }
    $oldIds = array_column($old, 'id');

    /* --- the channel id must belong to the handle (skipped when the page cannot be read) --- */
    try {
        [$st, $html] = by_get($pageBase . '/@' . $b['channel_handle']);
        if ($st === 200) {
            if (strpos($html, $b['channel_id']) !== false) {
                by_log('Channel id confirmed against the channel page.');
            } elseif (preg_match('/"(?:channelId|externalId)":"(UC[\w-]{22})"/', $html, $m)) {
                by_fail('channel_id ' . $b['channel_id'] . ' does not match the id on @' . $b['channel_handle'] . ' (' . $m[1] . ').');
            } else {
                by_log('WARN: channel id not found on the page; continuing.');
            }
        }
    } catch (Exception $e) {
        by_log('WARN: could not read the channel page to confirm the channel id (' . by_scrub($e->getMessage()) . '); continuing.');
    }

    /* --- discovery --- */
    $source = 'rss';
    $feed = null;
    $gone = [];
    if ($GLOBALS['by_key'] !== '') {
        try {
            [$feed, $gone] = by_fetch_api($b, $apiBase);
            $source = 'api';
        } catch (Exception $e) {
            by_log('WARN: the YouTube Data API call failed (' . by_scrub($e->getMessage()) . '); falling back to the public RSS feed.');
            $feed = null;
        }
    }
    if ($feed === null) {
        $feed = by_feed($b, $feedBase);
    }
    if (!$feed) {
        by_fail('the source contained no usable videos (wrong channel, empty or invalid response)');
    }
    $matched = array_values(array_filter($feed, function ($v) use ($b) { return by_eligible($v, $b); }));
    by_log('Source: ' . $source . '; entries read: ' . count($feed) . '; eligible Bayanath: ' . count($matched) . '; unrelated excluded: ' . (count($feed) - count($matched)) . '; published before: ' . count($old));
    if (!$matched) {
        by_fail('no entry matched the Bayanath filter. Set "playlist_id" or adjust "title_keywords" under "bayanath" in config.php.');
    }

    /* --- merge (fresh data wins; the array key removes duplicates), then verify every video --- */
    $merged = [];
    foreach ($old as $v) {
        $merged[$v['id']] = $v;
    }
    foreach ($matched as $v) {
        $merged[$v['id']] = $v;
    }
    foreach ($gone as $g) {
        unset($merged[$g]);
    }
    $list = array_values($merged);
    usort($list, function ($a, $b2) { return by_ts($b2['published'] ?? null) <=> by_ts($a['published'] ?? null); });
    $verified = [];
    foreach ($list as $v) {
        [$ok, $full] = by_oembed($oembedBase, $v['id']);
        if ($ok === true) {
            $v['title'] = by_repair_title((string) $v['title'], $full);
            if (empty($v['published'])) {
                $v['published'] = by_watch_date($watchBase, $v['id']);
            }
            $verified[] = $v;
        } elseif ($ok === null && in_array($v['id'], $oldIds, true)) {
            $verified[] = $v;
            by_log('WARN: could not re-check ' . $v['id'] . '; keeping the earlier entry');
        } else {
            by_log('Dropping ' . $v['id'] . ' (' . ($ok === false ? 'unavailable/private/deleted/not embeddable' : 'could not be verified') . ')');
        }
    }
    usort($verified, function ($a, $b2) { return by_ts($b2['published'] ?? null) <=> by_ts($a['published'] ?? null); });
    $verified = array_slice($verified, 0, $limit);
    if (!$verified) {
        by_fail('no video could be verified as public on YouTube');
    }
    $fields = function ($v) { return [$v['id'], $v['title'], $v['published'] ?? null, $v['thumbnail'] ?? null]; };
    if (array_map($fields, $verified) === array_map($fields, $old)) {
        by_log('No change: the published list is already up to date; nothing written.');
        $state['ok_slot'] = $slotKey;
        $state['last_ok'] = $now->format('c');
        if (!$dry) {
            by_state_write($stateFile, $state);
        }
        return;
    }
    $newIds = array_values(array_filter(array_column($verified, 'id'), function ($i) use ($oldIds) { return !in_array($i, $oldIds, true); }));
    $data = [
        'channel' => ['handle' => $b['channel_handle'], 'id' => $b['channel_id'], 'url' => 'https://www.youtube.com/@' . $b['channel_handle']],
        'updated' => gmdate('Y-m-d\TH:i:s\Z'),
        'videos' => array_map(function ($v) { return ['id' => $v['id'], 'title' => $v['title'], 'published' => $v['published'] ?? null, 'thumbnail' => $v['thumbnail']]; }, $verified),
    ];
    try {
        by_validate($data, $limit);
        $json = by_json($data);
        if (json_decode($json, true) !== $data) {
            throw new RuntimeException('not JSON round-trippable');
        }
    } catch (Exception $e) {
        by_fail('the result failed validation (' . $e->getMessage() . ')');
    }
    if ($dry) {
        by_log('Dry run: would write ' . count($verified) . ' videos; new: ' . count($newIds) . '; newest: ' . $verified[0]['title']);
        return;
    }
    try {
        by_backup($cache, $dataDir . '/bayanath-backup');
        by_write_atomic($cache, $json);
    } catch (Exception $e) {
        by_fail('could not write the published list: ' . $e->getMessage());
    }
    by_log('Wrote ' . count($verified) . ' videos to ' . basename($cache) . '; new: ' . count($newIds) . '; newest: ' . $verified[0]['title']);
    $state['ok_slot'] = $slotKey;
    $state['last_ok'] = $now->format('c');
    by_state_write($stateFile, $state);
}

by_main($argv);
