<?php
/* Form handler for the website (feedback, admissions enquiry, careers expression of interest).
   Called by public/api/submit.php. Lives OUTSIDE the public web folder (next to public_html on the hosting).
   Nothing here trusts the browser: every field is validated again, header injection is impossible (the subject is built from
   fixed words, a visitor's address is only ever used in Reply-To after filter_var), and an answer of "ok" is given only when the
   message was really handed to the mail system. A copy of every accepted submission is also kept in data/submissions/ (private). */
declare(strict_types=1);

const JAME_MAX_BODY = 24000;

const JAME_CHOICES = [
    'category' => ['appreciation' => 'Appreciation', 'suggestion' => 'Suggestion', 'facilities' => 'Facilities', 'academics' => 'Academics', 'admissions' => 'Admissions', 'other' => 'Other'],
    'audience' => ['student' => 'Student', 'parent' => 'Parent or guardian', 'alumni' => 'Alumnus or alumna', 'visitor' => 'Visitor', 'community' => 'Community member', 'other' => 'Other'],
    'about' => ['general' => 'The whole institution', 'masjid' => 'Jamia Masjid', 'schools' => 'English schools (nursery to high school)', 'pu' => 'Pre University College for Girls', 'degree' => 'Degree colleges', 'ncpul' => 'MMI-NCPUL Computer Centre', 'iti' => 'ITI', 'hifz' => 'Shoba-e-Hifz and Shoba-e-Alimiyath', 'banikuppa' => 'Residential School, Banikuppa', 'website' => 'This website'],
    'programme' => ['schools' => 'Nursery, primary or high school', 'pu' => 'Pre University College for Girls', 'degree' => 'Degree college (B.Com / BCA)', 'ncpul' => 'MMI-NCPUL Computer Centre', 'iti' => 'ITI (Fitter, MRAC, MMV)', 'hifz' => 'Shoba-e-Hifz / Shoba-e-Alimiyath', 'banikuppa' => 'Residential School, Banikuppa', 'unsure' => 'Not sure yet'],
    'area' => ['teaching-school' => 'Teaching: schools', 'teaching-college' => 'Teaching: colleges', 'islamic' => 'Islamic studies and Hifz', 'technical' => 'Technical training (ITI)', 'computer' => 'Computer education', 'admin' => 'Administration and office', 'residential' => 'Residential campus, Banikuppa', 'other' => 'Another way to contribute'],
    'experience' => ['fresher' => 'Starting out', 'one-three' => '1 to 3 years', 'three-five' => '3 to 5 years', 'five-plus' => 'More than 5 years'],
];

/* field => [type, required, max length (or choice list name), label]. type: text | line | phone | email | int | choice | bool */
const JAME_FORMS = [
    'feedback' => ['label' => 'Feedback', 'fields' => [
        'rating'   => ['int', true, 5, 'Rating'],
        'category' => ['choice', true, 'category', 'Topic'],
        'message'  => ['text', true, 2000, 'Message'],
        'about'    => ['choice', false, 'about', 'About'],
        'audience' => ['choice', false, 'audience', 'Sender is'],
        'name'     => ['line', false, 80, 'Name'],
        'email'    => ['email', false, 120, 'Email'],
    ], 'min' => ['message' => 5]],
    'admissions' => ['label' => 'Admissions enquiry', 'fields' => [
        'guardian'  => ['line', true, 80, 'Parent or guardian'],
        'phone'     => ['phone', true, 20, 'Phone'],
        'email'     => ['email', false, 120, 'Email'],
        'programme' => ['choice', true, 'programme', 'Programme'],
        'level'     => ['line', false, 60, 'Class or year sought'],
        'student'   => ['line', false, 80, 'Student name'],
        'message'   => ['text', false, 1000, 'Message'],
        'consent'   => ['bool', true, 0, 'Agrees to be contacted'],
    ], 'min' => []],
    'careers' => ['label' => 'Careers: expression of interest', 'fields' => [
        'name'          => ['line', true, 80, 'Name'],
        'phone'         => ['phone', true, 20, 'Phone'],
        'email'         => ['email', true, 120, 'Email'],
        'area'          => ['choice', true, 'area', 'Area of interest'],
        'qualification' => ['line', false, 120, 'Qualification'],
        'experience'    => ['choice', false, 'experience', 'Experience'],
        'message'       => ['text', false, 1500, 'Message'],
        'consent'       => ['bool', true, 0, 'Agrees to be contacted'],
    ], 'min' => []],
];

function jame_wants_json(): bool {
    return stripos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false;
}

/* One answer, then stop. JSON for the page script; a small stylesheet-only HTML page when the form was sent without JavaScript. */
function jame_reply(int $status, bool $ok, string $message, array $extra = []) {
    http_response_code($status);
    header('Cache-Control: no-store');
    header('X-Robots-Tag: noindex');
    if ($status === 405) {
        header('Allow: POST');
    }
    if (jame_wants_json()) {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => $ok, 'message' => $message] + $extra, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    }
    header('Content-Type: text/html; charset=utf-8');
    $title = $ok ? 'Thank you' : 'We could not send this';
    $ref = isset($extra['ref']) ? '<p class="cx-ref">Reference: ' . htmlspecialchars((string) $extra['ref'], ENT_QUOTES, 'UTF-8') . '</p>' : '';
    echo '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
        . '<title>' . $title . ' | Jame ul uloom</title><link rel="stylesheet" href="/portal-assets/portal.css"><link rel="stylesheet" href="/portal-assets/connect.css"></head>'
        . '<body class="page-connect"><main class="cx-plain"><div class="cx-card"><h1>' . $title . '</h1><p>' . htmlspecialchars($message, ENT_QUOTES, 'UTF-8') . '</p>' . $ref
        . '<p><a class="button" href="/index.html">Back to the website</a></p></div></main></body></html>';
    exit;
}

function jame_log(array $cfg, string $line): void {
    $dir = $cfg['data_dir'] . '/logs';
    if (!is_dir($dir)) {
        @mkdir($dir, 0700, true);
    }
    @file_put_contents($dir . '/forms.log', gmdate('Y-m-d\TH:i:s\Z') . ' ' . $line . "\n", FILE_APPEND | LOCK_EX);
}

/* The browser always sends Origin (or at least Referer) on a form post. Accept only our own host(s). */
function jame_origin_ok(array $cfg): bool {
    $src = $_SERVER['HTTP_ORIGIN'] ?? ($_SERVER['HTTP_REFERER'] ?? '');
    if ($src === '') {
        return false;
    }
    $host = parse_url($src, PHP_URL_HOST);
    return is_string($host) && in_array(strtolower($host), array_map('strtolower', $cfg['allowed_hosts']), true);
}

function jame_client_ip(array $cfg): string {
    $header = $cfg['ip_header'] ?? '';
    if ($header !== '' && !empty($_SERVER[$header])) {
        $ip = trim(explode(',', (string) $_SERVER[$header])[0]);
        if (filter_var($ip, FILTER_VALIDATE_IP)) {
            return $ip;
        }
    }
    return (string) ($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
}

/* Per visitor and overall limits, kept in small private files. Returns an error message, or '' when the submission may go on. */
function jame_rate_limit(array $cfg, string $ip): string {
    $dir = $cfg['data_dir'] . '/ratelimit';
    if (!is_dir($dir) && !@mkdir($dir, 0700, true)) {
        return '';   /* cannot keep counters: do not block honest visitors */
    }
    $now = time();
    $rate = $cfg['rate'] + ['per_ip_hour' => 5, 'per_ip_day' => 15, 'global_day' => 300];
    $check = function (string $name, array $limits) use ($dir, $now): string {
        $path = $dir . '/' . $name . '.json';
        $fh = @fopen($path, 'c+');
        if (!$fh) {
            return '';
        }
        flock($fh, LOCK_EX);
        $times = json_decode((string) stream_get_contents($fh), true);
        $times = is_array($times) ? array_values(array_filter($times, fn($t) => is_int($t) && $t > $now - 86400)) : [];
        $msg = '';
        foreach ($limits as $window => $max) {
            if (count(array_filter($times, fn($t) => $t > $now - $window)) >= $max) {
                $msg = 'Too many messages have been sent just now. Please wait a little and try again, or call the office.';
            }
        }
        if ($msg === '') {
            $times[] = $now;
            ftruncate($fh, 0);
            rewind($fh);
            fwrite($fh, json_encode($times));
        }
        flock($fh, LOCK_UN);
        fclose($fh);
        return $msg;
    };
    $key = hash('sha256', $ip . '|' . ($cfg['salt'] ?? 'jame'));
    $msg = $check('ip-' . $key, [3600 => $rate['per_ip_hour'], 86400 => $rate['per_ip_day']]);
    return $msg !== '' ? $msg : $check('all', [86400 => $rate['global_day']]);
}

function jame_clean(string $s, bool $multiline): string {
    $s = str_replace("\0", '', $s);
    if (!mb_check_encoding($s, 'UTF-8')) {
        return '';
    }
    $s = str_replace("\r\n", "\n", $s);
    $s = preg_replace($multiline ? '/[^\P{C}\n]/u' : '/\p{C}/u', $multiline ? '' : ' ', $s) ?? '';
    if (!$multiline) {
        $s = preg_replace('/\s+/u', ' ', $s) ?? '';
    } else {
        $s = preg_replace("/\n{3,}/", "\n\n", $s) ?? '';
    }
    return trim($s);
}

/* Returns [clean values, errors by field]. */
function jame_validate(string $form, array $in): array {
    $def = JAME_FORMS[$form];
    $out = [];
    $err = [];
    foreach ($def['fields'] as $name => [$type, $required, $limit, $label]) {
        $raw = $in[$name] ?? '';
        if (is_array($raw)) {
            $err[$name] = $label . ' is not valid.';
            continue;
        }
        $raw = (string) $raw;
        $v = '';
        switch ($type) {
            case 'bool':
                $v = in_array(strtolower($raw), ['1', 'on', 'yes', 'true'], true) ? 'yes' : '';
                break;
            case 'int':
                $v = ctype_digit($raw) && (int) $raw >= 1 && (int) $raw <= $limit ? (string) (int) $raw : '';
                if ($raw !== '' && $v === '') {
                    $err[$name] = 'Please choose a rating from 1 to ' . $limit . '.';
                }
                break;
            case 'choice':
                $v = array_key_exists($raw, JAME_CHOICES[$limit]) ? $raw : '';
                if ($raw !== '' && $v === '') {
                    $err[$name] = 'Please choose one of the options.';
                }
                break;
            case 'phone':
                $v = jame_clean($raw, false);
                $digits = preg_replace('/\D/', '', $v) ?? '';
                if ($v !== '' && (!preg_match('/^[0-9 +()\-]{7,20}$/', $v) || strlen($digits) < 7 || strlen($digits) > 15)) {
                    $err[$name] = 'Please enter a phone number we can call.';
                    $v = '';
                }
                break;
            case 'email':
                $v = jame_clean($raw, false);
                if ($v !== '' && (strlen($v) > $limit || !filter_var($v, FILTER_VALIDATE_EMAIL) || preg_match('/[\r\n,;<>"]/', $v))) {
                    $err[$name] = 'Please enter a valid email address.';
                    $v = '';
                }
                break;
            default:
                $v = jame_clean($raw, $type === 'text');
                if (mb_strlen($v) > $limit) {
                    $err[$name] = $label . ' is too long (at most ' . $limit . ' characters).';
                    $v = '';
                }
                $min = $def['min'][$name] ?? 0;
                if ($v !== '' && mb_strlen($v) < $min) {
                    $err[$name] = 'Please write a little more (at least ' . $min . ' characters).';
                    $v = '';
                }
        }
        if ($v === '' && $required && !isset($err[$name])) {
            $err[$name] = $type === 'bool' ? 'Please tick the box so that we may contact you.' : 'Please fill in: ' . $label . '.';
        }
        $out[$name] = $v;
    }
    return [$out, $err];
}

function jame_reference(string $form): string {
    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    $s = '';
    for ($i = 0; $i < 6; $i++) {
        $s .= $alphabet[random_int(0, strlen($alphabet) - 1)];
    }
    return 'JU-' . strtoupper(substr($form, 0, 2)) . '-' . $s;
}

function jame_lines(string $form, array $v, string $ref): string {
    $def = JAME_FORMS[$form];
    $lines = [$def['label'] . ' received through the website', 'Reference: ' . $ref, 'Received: ' . gmdate('Y-m-d H:i') . ' UTC', ''];
    foreach ($def['fields'] as $name => [$type, , $limit, $label]) {
        if ($v[$name] === '' || $name === 'consent') {
            continue;
        }
        $val = $type === 'choice' ? JAME_CHOICES[$limit][$v[$name]] : ($type === 'int' ? $v[$name] . ' of ' . $limit . ' stars' : $v[$name]);
        $lines[] = $label . ': ' . ($type === 'text' ? "\n" . $val . "\n" : $val);
    }
    if (isset($v['consent'])) {
        $lines[] = 'The sender agreed to be contacted about this message.';
    }
    $lines[] = '';
    $lines[] = '--';
    $lines[] = 'Sent from the website form. Reply to this email to answer the sender (when they gave an address).';
    return implode("\n", $lines);
}

function jame_subject(string $form, array $v): string {
    $def = JAME_FORMS[$form];
    $s = '[Jame ul uloom website] ' . $def['label'];
    if ($form === 'feedback') {
        $s .= ': ' . $v['rating'] . ' of 5, ' . JAME_CHOICES['category'][$v['category']];
    } elseif ($form === 'admissions') {
        $s .= ': ' . JAME_CHOICES['programme'][$v['programme']];
    } else {
        $s .= ': ' . JAME_CHOICES['area'][$v['area']];
    }
    return $s;
}

function jame_send(array $cfg, string $form, array $v, string $ref): bool {
    $subject = jame_subject($form, $v);
    $body = jame_lines($form, $v, $ref);
    $headers = ['From: Jame ul uloom website <' . $cfg['mail_from'] . '>', 'MIME-Version: 1.0', 'Content-Type: text/plain; charset=UTF-8', 'Content-Transfer-Encoding: 8bit', 'X-Mailer: jame-forms'];
    if (!empty($v['email'])) {
        $headers[] = 'Reply-To: ' . $v['email'];   /* already checked by filter_var and free of line breaks */
    }
    $to = implode(', ', $cfg['mail_to']);
    if (($cfg['mail_driver'] ?? 'mail') === 'file') {
        $dir = $cfg['data_dir'] . '/outbox';
        if (!is_dir($dir) && !@mkdir($dir, 0700, true)) {
            return false;
        }
        return @file_put_contents($dir . '/' . $ref . '.eml', 'To: ' . $to . "\r\nSubject: " . $subject . "\r\n" . implode("\r\n", $headers) . "\r\n\r\n" . $body) !== false;
    }
    return @mail($to, $subject, $body, implode("\r\n", $headers), '-f' . $cfg['mail_from']);
}

/* A private copy, one line of JSON per submission, so nothing is lost if the mail system misbehaves. */
function jame_store(array $cfg, string $form, array $v, string $ref, bool $mailed): bool {
    $dir = $cfg['data_dir'] . '/submissions';
    if (!is_dir($dir) && !@mkdir($dir, 0700, true)) {
        return false;
    }
    $path = $dir . '/' . gmdate('Y-m') . '.jsonl';
    $new = !file_exists($path);
    $line = json_encode(['ref' => $ref, 'form' => $form, 'at' => gmdate('c'), 'mailed' => $mailed, 'data' => $v], JSON_UNESCAPED_UNICODE) . "\n";
    $ok = @file_put_contents($path, $line, FILE_APPEND | LOCK_EX) !== false;
    if ($ok && $new) {
        @chmod($path, 0600);
    }
    return $ok;
}

function jame_handle(array $cfg): void {
    $cfg += ['rate' => [], 'allowed_hosts' => [], 'min_fill_seconds' => 2];
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        jame_reply(405, false, 'This address only accepts the website forms.');
    }
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > JAME_MAX_BODY) {
        jame_reply(413, false, 'That message is too large. Please shorten it and try again.');
    }
    if (!jame_origin_ok($cfg)) {
        jame_log($cfg, 'rejected: origin');
        jame_reply(403, false, 'This form can only be sent from the Jame ul uloom website.');
    }
    $form = (string) ($_POST['form'] ?? '');
    if (!isset(JAME_FORMS[$form])) {
        jame_reply(400, false, 'This form is not recognised.');
    }
    if (trim((string) ($_POST['website'] ?? '')) !== '') {   /* hidden field that only robots fill in */
        jame_log($cfg, 'rejected: honeypot (' . $form . ')');
        jame_reply(400, false, 'This message could not be accepted.');
    }
    $opened = (int) ($_POST['opened'] ?? 0);   /* milliseconds since the page was opened, measured in the browser */
    if ($opened > 0 && $opened < (int) $cfg['min_fill_seconds'] * 1000) {
        jame_log($cfg, 'rejected: too fast (' . $form . ')');
        jame_reply(400, false, 'That was very quick. Please take a moment to check your message and send it again.');
    }
    [$values, $errors] = jame_validate($form, $_POST);
    if ($errors) {
        jame_reply(422, false, 'Please check the highlighted fields.', ['errors' => $errors]);
    }
    $limited = jame_rate_limit($cfg, jame_client_ip($cfg));
    if ($limited !== '') {
        jame_log($cfg, 'rejected: rate limit (' . $form . ')');
        jame_reply(429, false, $limited);
    }
    $ref = jame_reference($form);
    $mailed = jame_send($cfg, $form, $values, $ref);
    $stored = jame_store($cfg, $form, $values, $ref, $mailed);
    jame_log($cfg, ($mailed ? 'sent ' : 'MAIL FAILED ') . $form . ' ' . $ref . ($stored ? '' : ' (not stored)'));
    if (!$mailed) {
        jame_reply(503, false, 'We could not send your message just now. Please try again in a few minutes, or call or email the office directly.');
    }
    jame_reply(200, true, 'Your message has reached the Jame ul uloom office.', ['ref' => $ref]);
}
