const puppeteer = require('puppeteer');
const { CHROMIUM_ARGS } = require('./launch-args');

const CHROMIUM_PATH = process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium';
const TIMEOUT_MS = 45000;

// When LAUNCH_CHECK_STOP_PID1=1, signal supervisord (PID 1) to exit after the
// check so the CI step returns instead of hanging on the supervisor.
function stopSupervisorIfRequested() {
    if (process.env.LAUNCH_CHECK_STOP_PID1 === '1') {
        try { process.kill(1, 'SIGTERM'); } catch (_) { /* ignore */ }
    }
}

const timer = setTimeout(() => {
    console.error('LAUNCH_CHECK_TIMEOUT: browser did not become ready in time');
    stopSupervisorIfRequested();
    process.exit(1);
}, TIMEOUT_MS);

(async () => {
    let browser;
    try {
        browser = await puppeteer.launch({
            headless: 'shell',
            executablePath: CHROMIUM_PATH,
            args: CHROMIUM_ARGS
        });

        const version = await browser.version();
        const page = await browser.newPage();
        await page.goto('about:blank');
        await page.close();

        console.log(`Browser launched and controllable: ${version}`);
        console.log('LAUNCH_CHECK_OK');
        await browser.close();
        clearTimeout(timer);
        stopSupervisorIfRequested();
        process.exit(0);
    } catch (error) {
        console.error('LAUNCH_CHECK_FAILED:', error.message);
        console.error(error.stack);
        if (browser) {
            try { await browser.close(); } catch (_) { /* ignore */ }
        }
        clearTimeout(timer);
        stopSupervisorIfRequested();
        process.exit(1);
    }
})();
