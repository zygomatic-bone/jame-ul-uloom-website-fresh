<?php
/* Entry point of the website forms. All the work is done by jame-server/forms.php, which sits OUTSIDE the public folder
   (next to public_html on the hosting). If the server folder is somewhere else, set JAME_SERVER_DIR in .htaccess (SetEnv). */
declare(strict_types=1);

$dir = getenv('JAME_SERVER_DIR') ?: dirname(__DIR__, 2) . '/jame-server';
$cfgFile = getenv('JAME_CONFIG') ?: $dir . '/config.php';
header('Content-Type: application/json; charset=utf-8');
if (!is_file($dir . '/forms.php') || !is_file($cfgFile)) {
    http_response_code(503);
    header('Cache-Control: no-store');
    echo '{"ok":false,"message":"The forms are not set up on this server yet. Please call or email the office."}';
    exit;
}
require $dir . '/forms.php';
$cfg = require $cfgFile;
$cfg['data_dir'] = $cfg['data_dir'] ?? $dir . '/data';
jame_handle($cfg);
