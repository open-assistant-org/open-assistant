// --no-zygote: safe now that dumb-init is PID 1 (not supervisord). With dumb-init
// as PID 1, Chrome's child processes are never stolen by a competing waitpid() call.
// --disable-features=MediaRouter: belt-and-suspenders so Chrome doesn't try to
// talk to DBus for features we don't need even when the bus is available.
const CHROMIUM_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--disable-gpu',
    '--disable-features=MediaRouter,OptimizationHints,TranslateUI'
];

module.exports = { CHROMIUM_ARGS };
