<?php
/* Copy this file to config.php (same folder) and edit it. config.php is never published and must not be readable from the web:
   keep the whole jame-server folder next to public_html, not inside it. */
return [
    // Where messages are delivered. The email address printed on the website.
    'mail_to' => ['jamiaululoom@gmail.com'],
    // Sender shown on the messages. Use a real mailbox on the website's own domain (create one in cPanel, Email Accounts);
    // mail from an unknown address is often treated as spam.
    'mail_from' => 'website@jameululoom.org',
    // 'mail' = the hosting's normal mail system. 'file' = write the message into data/outbox/ instead (for testing only).
    'mail_driver' => 'mail',
    // Only forms sent from these host names are accepted.
    'allowed_hosts' => ['jameululoom.org', 'www.jameululoom.org'],
    // A long random text, used to hide visitors' addresses in the rate-limit file names. Change it once.
    'salt' => 'change-this-to-a-long-random-text',
    // Private folder for copies of submissions, the rate-limit counters and logs. Default: jame-server/data
    // 'data_dir' => '/home/ACCOUNT/jame-server/data',
    // Messages allowed per visitor and overall.
    'rate' => ['per_ip_hour' => 5, 'per_ip_day' => 15, 'global_day' => 300],
    // Forms sent faster than this after the page opened are refused (robots).
    'min_fill_seconds' => 2,
    // Only if the site sits behind a proxy such as Cloudflare: the server variable that holds the visitor's address,
    // for example 'HTTP_CF_CONNECTING_IP'. Leave empty otherwise.
    'ip_header' => '',
    // Optional YouTube Data API key for the Bayanath updater (bayanath-update.php). Leave empty to use the public RSS feed.
    'youtube_api_key' => '',
    // Bayanath updater (bayanath-update.php). Everything here is optional: the defaults are the verified channel and a
    // Saturday 21:00 India-time slot. Uncomment 'cache' only if your public folder is not called public_html.
    // 'bayanath' => [
    //     'cache' => '/home/ACCOUNT/public_html/data/bayanath-videos.json',   // the file visitors' browsers read
    //     'max_videos' => 10,
    // ],
];
