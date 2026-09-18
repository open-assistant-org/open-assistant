/**
 * Theme runtime. Loaded synchronously in <head>, BEFORE common.css and any
 * page <style> block, so the resolved theme is applied to <html> before
 * first paint. Every page is a full navigation (no SPA router), so this
 * file runs fresh on every load and must not depend on common.js (which
 * loads later).
 *
 * Preference is one of 'light' | 'dark' | 'system' and lives in two places:
 *   - localStorage['oa-theme']   fast, synchronous, read here before paint.
 *   - the appearance.theme DB setting, durable and cross-device.
 * localStorage is a cache; the DB value wins once settings load (see
 * settings.js loadCategory('appearance') and reconcileThemeFromServer()).
 */
(function () {
    var STORAGE_KEY = 'oa-theme';
    var DEFAULT_PREFERENCE = 'system';
    var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

    function isValidPreference(value) {
        return value === 'light' || value === 'dark' || value === 'system';
    }

    function readPreference() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return DEFAULT_PREFERENCE;
            var value = JSON.parse(raw);
            return isValidPreference(value) ? value : DEFAULT_PREFERENCE;
        } catch (e) {
            // Private browsing / blocked storage / corrupt value - fall back quietly.
            return DEFAULT_PREFERENCE;
        }
    }

    function resolve(preference) {
        if (preference === 'light' || preference === 'dark') return preference;
        return (media && media.matches) ? 'light' : 'dark';
    }

    function updateMetaThemeColor(resolved) {
        var color = resolved === 'light' ? '#f4f6f8' : '#0f0f0f';
        var themeColorTag = document.querySelector('meta[name="theme-color"]');
        if (themeColorTag) themeColorTag.setAttribute('content', color);

        var statusBarTag = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
        if (statusBarTag) statusBarTag.setAttribute('content', resolved === 'light' ? 'default' : 'black-translucent');
    }

    function apply(preference) {
        var resolved = resolve(preference);
        var root = document.documentElement;
        root.setAttribute('data-theme', resolved);
        root.style.colorScheme = resolved;
        updateMetaThemeColor(resolved);
        return resolved;
    }

    function setTheme(preference) {
        if (!isValidPreference(preference)) preference = DEFAULT_PREFERENCE;
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(preference));
        } catch (e) {
            // Ignore - theme still applies for this page load, just won't persist.
        }
        return apply(preference);
    }

    // Apply immediately, before the stylesheet loads, to avoid a flash.
    apply(readPreference());

    // System mode must react live to OS changes, without a reload.
    if (media && media.addEventListener) {
        media.addEventListener('change', function () {
            if (readPreference() === 'system') apply('system');
        });
    } else if (media && media.addListener) {
        // Safari < 14 fallback.
        media.addListener(function () {
            if (readPreference() === 'system') apply('system');
        });
    }

    window.theme = {
        get: readPreference,
        set: setTheme,
        apply: apply,
        resolve: resolve
    };
})();
