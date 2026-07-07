// --no-zygote omitted: under supervisord-as-PID-1 it causes child processes to be
// reaped before Chromium can wait() on them → "Failed to launch the browser process".
// --disable-features=MediaRouter: MediaRouter connects to dbus on startup; without
// dbus in the container this causes a signal-kill crash (Code: null). Belt-and-
// suspenders alongside headless:'shell', which skips these features by default.
const CHROMIUM_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--disable-gpu',
    '--disable-features=MediaRouter,OptimizationHints,TranslateUI'
];

module.exports = { CHROMIUM_ARGS };
