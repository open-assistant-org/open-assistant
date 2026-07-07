// --no-zygote omitted: under supervisord-as-PID-1, it causes Chromium's child
// processes to be reaped by the container init before Chromium can wait() on them,
// aborting the launch ("Failed to launch the browser process: Code: null").
const CHROMIUM_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--disable-gpu',
    '--disable-dbus'
];

module.exports = { CHROMIUM_ARGS };
