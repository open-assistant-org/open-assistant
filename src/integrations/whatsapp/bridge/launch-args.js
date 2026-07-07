/**
 * Chromium launch flags for the WhatsApp bridge.
 *
 * Kept in a shared module so the runtime bridge (server.js) and the build-time
 * launch check (launch-check.js) always use the exact same flags and cannot drift.
 *
 * NOTE: `--no-zygote` is deliberately absent. Under supervisord (PID 1) the
 * container's init reaps Chromium's child processes; without a zygote Chromium
 * forks those children directly and must wait() on them itself, so the PID-1
 * reaper steals them and the browser aborts its launch ("Failed to launch the
 * browser process: Code: null"). Keeping the zygote lets Chromium manage its own
 * process subtree, which is also what Puppeteer's recommended Docker args do.
 */
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
