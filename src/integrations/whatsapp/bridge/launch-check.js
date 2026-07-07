/**
 * Build-time Chromium launch check for the WhatsApp bridge.
 *
 * Launches Chromium with the exact production flags (from launch-args.js) and
 * confirms the browser process actually comes up and is controllable, then exits.
 *
 * This is meant to run under supervisord as PID 1 during the Docker build (see
 * supervisord.validate.conf) so it reproduces the runtime condition that caused
 * "Failed to launch the browser process: Code: null" — namely PID 1 reaping
 * Chromium's child processes. On success it prints LAUNCH_CHECK_OK; on any
 * failure it exits non-zero, failing the build.
 */
const puppeteer = require('puppeteer');
const { CHROMIUM_ARGS } = require('./launch-args');

const CHROMIUM_PATH = process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium';
const TIMEOUT_MS = 45000;

/**
 * When run under supervisord-as-PID-1 (the build validation), supervisord stays
 * up after this one-shot check exits. Signal it to shut down gracefully so the
 * Docker RUN step returns instead of waiting for the outer timeout. Gated behind
 * an env var so running this script in a normal shell never signals system init.
 */
function stopSupervisorIfRequested() {
    if (process.env.LAUNCH_CHECK_STOP_PID1 === '1') {
        try { process.kill(1, 'SIGTERM'); } catch (_) { /* ignore */ }
    }
}

// Hard safety timeout so a hung launch fails the build instead of blocking it.
const timer = setTimeout(() => {
    console.error('❌ LAUNCH_CHECK_TIMEOUT: browser did not become ready in time');
    stopSupervisorIfRequested();
    process.exit(1);
}, TIMEOUT_MS);

(async () => {
    let browser;
    try {
        console.log(`🔎 Launching Chromium at ${CHROMIUM_PATH} with production flags...`);
        browser = await puppeteer.launch({
            headless: true,
            executablePath: CHROMIUM_PATH,
            args: CHROMIUM_ARGS
        });

        // Prove the browser is actually controllable, not just spawned.
        const version = await browser.version();
        const page = await browser.newPage();
        await page.goto('about:blank');
        await page.close();

        console.log(`✅ Browser launched and controllable: ${version}`);
        console.log('LAUNCH_CHECK_OK');
        await browser.close();
        clearTimeout(timer);
        stopSupervisorIfRequested();
        process.exit(0);
    } catch (error) {
        console.error('❌ LAUNCH_CHECK_FAILED:', error.message);
        console.error(error.stack);
        if (browser) {
            try { await browser.close(); } catch (_) { /* ignore */ }
        }
        clearTimeout(timer);
        stopSupervisorIfRequested();
        process.exit(1);
    }
})();
