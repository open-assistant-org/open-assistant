/**
 * PWA functionality: Service Worker registration and install prompt
 */

let deferredPrompt = null;
let installButton = null;

/**
 * Register the service worker
 */
async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) {
        console.log('Service Workers not supported');
        return;
    }

    try {
        const base = window.INSTANCE_BASE_PATH || '';
        const registration = await navigator.serviceWorker.register(
            base + '/service-worker.js',
            { scope: base + '/' }
        );

        console.log('Service Worker registered:', registration.scope);

        // Handle updates
        registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            console.log('Service Worker update found');

            newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                    // New service worker available
                    showUpdateNotification();
                }
            });
        });

        // Listen for controlling service worker changes
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            console.log('Service Worker controller changed, reloading...');
            window.location.reload();
        });

    } catch (error) {
        // A missing/unreachable service worker (e.g. a 404 from a reverse
        // proxy that doesn't route /service-worker.js) is non-fatal: the app
        // works fully without offline support. Log it as a warning rather than
        // an error so it doesn't look like a breaking failure.
        console.warn('Service Worker not registered (offline support disabled):', error.message);
    }
}

/**
 * Show notification when update is available
 */
function showUpdateNotification() {
    toast.info('New version available! Reload to update.');
}

/**
 * Update the service worker
 */
window.updateServiceWorker = async function() {
    const registration = await navigator.serviceWorker.getRegistration();
    if (registration && registration.waiting) {
        // Tell the waiting service worker to skip waiting
        registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
};

/**
 * Handle PWA install prompt
 */
window.addEventListener('beforeinstallprompt', (e) => {
    console.log('Install prompt triggered');

    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();

    // Stash the event so it can be triggered later
    deferredPrompt = e;

    // Show install button if it exists
    showInstallButton();
});

/**
 * Show install button in UI
 */
function showInstallButton() {
    // Check if install button already exists
    installButton = document.getElementById('installAppBtn');

    if (!installButton) {
        // Create install button dynamically
        installButton = document.createElement('button');
        installButton.id = 'installAppBtn';
        installButton.className = 'nav-link';
        installButton.textContent = '📱 Install';
        installButton.style.cssText = `
            background: rgba(0, 255, 0, 0.1);
            border: 1px solid #00ff00;
            color: #00ff00;
        `;

        // Add to navbar
        const navbarLinks = document.querySelector('.navbar-links');
        if (navbarLinks) {
            navbarLinks.appendChild(installButton);
        }
    }

    if (installButton) {
        installButton.style.display = 'inline-block';
        installButton.addEventListener('click', promptInstall);
    }
}

/**
 * Hide install button
 */
function hideInstallButton() {
    if (installButton) {
        installButton.style.display = 'none';
    }
}

/**
 * Prompt user to install PWA
 */
async function promptInstall() {
    if (!deferredPrompt) {
        console.log('Install prompt not available');
        return;
    }

    // Show the install prompt
    deferredPrompt.prompt();

    // Wait for the user's response
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`User response to install prompt: ${outcome}`);

    // Clear the deferred prompt
    deferredPrompt = null;

    // Hide the install button
    hideInstallButton();
}

/**
 * Track if app is installed
 */
window.addEventListener('appinstalled', () => {
    console.log('PWA installed successfully');
    hideInstallButton();

    // Show success message
    toast.success('App installed successfully!');
});

/**
 * Detect if running as installed PWA
 */
function isInstalledPWA() {
    // Check if running in standalone mode
    if (window.matchMedia('(display-mode: standalone)').matches) {
        return true;
    }

    // Check if running in iOS standalone mode
    if (window.navigator.standalone === true) {
        return true;
    }

    return false;
}

/**
 * Check for app updates (version check)
 */
async function checkForAppUpdates() {
    try {
        const response = await fetch((window.INSTANCE_BASE_PATH || '') + '/health');
        const data = await response.json();

        // Store current version
        const storedVersion = localStorage.getItem('app_version');
        const currentVersion = data.version;

        if (storedVersion && storedVersion !== currentVersion) {
            console.log(`App updated: ${storedVersion} → ${currentVersion}`);
            toast.success(`Updated to version ${currentVersion}`);
        }

        // Update stored version
        localStorage.setItem('app_version', currentVersion);

    } catch (error) {
        console.error('Failed to check for updates:', error);
    }
}

/**
 * Initialize PWA features
 */
function initPWA() {
    console.log('Initializing PWA features...');

    // Register service worker
    registerServiceWorker();

    // Check version on load
    checkForAppUpdates();

    // Log if running as installed app
    if (isInstalledPWA()) {
        console.log('Running as installed PWA');
        document.body.classList.add('is-pwa');
    }

}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPWA);
} else {
    initPWA();
}

// Export for use in other scripts
window.PWA = {
    registerServiceWorker,
    promptInstall,
    isInstalledPWA,
    checkForAppUpdates
};
