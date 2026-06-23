"""Automatic cookie consent popup detection and dismissal.

Handles the most common cookie consent management platforms (OneTrust,
Cookiebot, TrustArc, CookieYes, Klaro, Complianz, etc.) as well as
generic "Accept cookies" banners that follow typical naming conventions.

The approach is deliberately aggressive about accepting: for an automated
browser that doesn't persist cookies across sessions, the fastest path
through a consent dialog is always "accept all".
"""

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# JavaScript executed *once* after each navigation to dismiss cookie popups.
# Strategy:
#   1. Try platform-specific selectors first (most reliable).
#   2. Fall back to text-matching on visible buttons/links.
#   3. As a last resort, try removing common overlay containers via CSS class
#      patterns so the page is at least usable.
# ---------------------------------------------------------------------------

DISMISS_COOKIE_CONSENT_JS = """
() => {
    const ACCEPT_PATTERNS = [
        /^accept(\\s+(all|cookies?|&\\s*(close|continue|proceed)))?$/i,
        /^(i\\s+)?accept(\\s+all)?$/i,
        /^(i )?agree(\\s+to all)?$/i,
        /^allow\\s*(all)?\\s*(cookies?)?$/i,
        /^(got it|ok|okay|sure)$/i,
        /^yes,? i('m| am) (happy|fine|ok)/i,
        /^continue$/i,
        /^consent$/i,
        /^confirm(\\s+my)?\\s*(choice)?s?$/i,
        /^close$/i,
        /^dismiss$/i,
        /^agree\\s*(&|and)?\\s*(close|continue|proceed)?$/i,
        /^save\\s*(preferences|settings|&\\s*(exit|close))?$/i,
        /^that'?s\\s*(fine|ok)$/i,
    ];

    const REJECT_PATTERNS = [
        /reject/i,
        /decline/i,
        /deny/i,
        /manage/i,
        /settings/i,
        /preferences/i,
        /customise/i,
        /customize/i,
    ];

    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function textOf(el) {
        return (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
    }

    function matchesAccept(text) {
        return ACCEPT_PATTERNS.some(p => p.test(text));
    }

    function matchesReject(text) {
        return REJECT_PATTERNS.some(p => p.test(text));
    }

    // --- 1. Platform-specific selectors (ordered by prevalence) -----------

    const platformSelectors = [
        // OneTrust
        '#onetrust-accept-btn-handler',
        '.onetrust-close-btn-handler',
        // Cookiebot
        '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
        '#CybotCookiebotDialogBodyButtonAccept',
        'a[id="CybotCookiebotDialogBodyLevelButtonAccept"]',
        // TrustArc / TrustE
        '.trustarc-agree-btn',
        '#truste-consent-button',
        // CookieYes / CookieLaw
        '.cky-btn-accept',
        '#cookie_action_close_header',
        // Quantcast
        '.qc-cmp2-summary-buttons button[mode="primary"]',
        // Klaro
        '.klaro .cm-btn-accept',
        '.klaro .cm-btn-accept-all',
        // Complianz
        '.cmplz-accept',
        // Borlabs
        '#BorlabsCookieBox a[data-cookie-accept-all]',
        // Cookie Notice (by dFactory)
        '#cn-accept-cookie',
        // GDPR Cookie Consent
        '#cookie_accept',
        '#gdpr-cookie-accept',
        // Osano
        '.osano-cm-accept-all',
        // Didomi
        '#didomi-notice-agree-button',
        // Iubenda
        '.iubenda-cs-accept-btn',
        // Generic common patterns
        'button[data-cookieconsent="accept"]',
        'button[data-action="accept"]',
        'a[data-cookieconsent="accept"]',
    ];

    for (const sel of platformSelectors) {
        try {
            const el = document.querySelector(sel);
            if (el && isVisible(el)) {
                el.click();
                return {dismissed: true, method: 'platform', selector: sel};
            }
        } catch (_) { /* selector may be invalid in some edge cases */ }
    }

    // --- 2. Text-matching on buttons / links inside likely containers -----

    // Identify candidate containers: elements whose id/class/role suggests
    // a cookie consent banner.
    const CONTAINER_PATTERNS = [
        /cookie/i, /consent/i, /gdpr/i, /privacy/i,
        /cc[-_]?banner/i, /notice/i, /compliance/i,
    ];

    function isCookieContainer(el) {
        const id = el.id || '';
        const cls = el.className || '';
        const role = el.getAttribute('role') || '';
        const text = id + ' ' + cls + ' ' + role;
        return CONTAINER_PATTERNS.some(p => p.test(text));
    }

    // Collect all visible buttons and link-like elements
    const clickables = [
        ...document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]')
    ].filter(isVisible);

    // First pass: find accept buttons inside a cookie-related container
    for (const el of clickables) {
        const text = textOf(el);
        if (!text || text.length > 60) continue;  // skip long text (not a button label)
        if (matchesAccept(text) && !matchesReject(text)) {
            // Check if this element or a parent looks like a cookie banner
            let parent = el.parentElement;
            let depth = 0;
            while (parent && depth < 8) {
                if (isCookieContainer(parent)) {
                    el.click();
                    return {dismissed: true, method: 'text_in_container', text: text};
                }
                parent = parent.parentElement;
                depth++;
            }
        }
    }

    // Second pass: accept button anywhere on the page (less confident)
    // Only if there's a visible cookie-related container on the page
    const allElements = document.querySelectorAll('*');
    let hasCookieBanner = false;
    for (const el of allElements) {
        if (isVisible(el) && isCookieContainer(el)) {
            hasCookieBanner = true;
            break;
        }
    }

    if (hasCookieBanner) {
        for (const el of clickables) {
            const text = textOf(el);
            if (!text || text.length > 60) continue;
            if (matchesAccept(text) && !matchesReject(text)) {
                el.click();
                return {dismissed: true, method: 'text_global', text: text};
            }
        }
    }

    // --- 3. [role="dialog"] / [role="alertdialog"] close or accept buttons --
    // Handles consent dialogs that use ARIA dialog roles (many modern CMPs).
    const dialogs = document.querySelectorAll('[role="dialog"], [role="alertdialog"]');
    for (const dialog of dialogs) {
        if (!isVisible(dialog)) continue;
        const dialogText = (dialog.innerText || dialog.textContent || '').toLowerCase();
        const looksLikeCookieBanner = /cookie|consent|gdpr|privacy|tracking|analytics/.test(dialogText);
        if (!looksLikeCookieBanner) continue;

        // Try accept-labelled button first
        const buttons = dialog.querySelectorAll('button, [role="button"], a');
        for (const btn of buttons) {
            const text = textOf(btn);
            if (!text || text.length > 60) continue;
            if (matchesAccept(text) && !matchesReject(text)) {
                btn.click();
                return {dismissed: true, method: 'dialog_accept', text: text};
            }
        }
        // Fall back to close/X button within the dialog
        const closeBtn = dialog.querySelector('[aria-label*="close" i], [aria-label*="dismiss" i], .close, .dismiss, button[class*="close"]');
        if (closeBtn && isVisible(closeBtn)) {
            closeBtn.click();
            return {dismissed: true, method: 'dialog_close'};
        }
    }

    // --- 4. Last resort: hide cookie overlay containers via CSS --------------
    // This doesn't "accept" cookies but unblocks the page so the agent can
    // continue. Only triggered if we found a banner but couldn't click it.
    const OVERLAY_SELECTORS = [
        '#onetrust-consent-sdk',
        '#cookieConsentContainer',
        '#cookie-law-info-bar',
        '#cookie-notice',
        '.cookie-notice',
        '.cookie-banner',
        '.cookie-consent',
        '.cookie-overlay',
        '.gdpr-overlay',
        '.cc-window',
        '[id*="cookie-banner"]',
        '[id*="cookie-consent"]',
        '[id*="cookieBanner"]',
        '[class*="cookie-banner"]',
        '[class*="cookieBanner"]',
    ];

    let removedOverlay = false;
    for (const sel of OVERLAY_SELECTORS) {
        try {
            const el = document.querySelector(sel);
            if (el && isVisible(el)) {
                el.style.display = 'none';
                removedOverlay = true;
            }
        } catch (_) {}
    }
    // Restore body scroll if a banner was locking it
    if (removedOverlay) {
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        return {dismissed: true, method: 'overlay_hidden'};
    }

    // --- 5. Nothing found --------------------------------------------------
    return {dismissed: false};
}
"""

# ---------------------------------------------------------------------------
# Lighter-weight init script injected into every page context.  It sets up a
# MutationObserver that watches for dynamically-inserted cookie banners
# (many consent managers load asynchronously via a <script> tag and inject
# their UI after DOMContentLoaded).
# ---------------------------------------------------------------------------

COOKIE_CONSENT_INIT_SCRIPT = """
(() => {
    // Avoid double-init
    if (window.__cookieConsentObserverInstalled) return;
    window.__cookieConsentObserverInstalled = true;

    const PLATFORM_SELECTORS = [
        '#onetrust-accept-btn-handler',
        '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
        '#CybotCookiebotDialogBodyButtonAccept',
        '.trustarc-agree-btn',
        '#truste-consent-button',
        '.cky-btn-accept',
        '.qc-cmp2-summary-buttons button[mode="primary"]',
        '.klaro .cm-btn-accept-all',
        '.klaro .cm-btn-accept',
        '.cmplz-accept',
        '#cn-accept-cookie',
        '.osano-cm-accept-all',
        '#didomi-notice-agree-button',
        '.iubenda-cs-accept-btn',
        'button[data-cookieconsent="accept"]',
    ];

    const ACCEPT_RE = [
        /^accept(\\s+(all|cookies?|&\\s*(close|continue|proceed)))?$/i,
        /^(i\\s+)?accept(\\s+all)?$/i,
        /^(i )?agree(\\s+to all)?$/i,
        /^allow\\s*(all)?\\s*(cookies?)?$/i,
        /^(got it|ok|okay|sure|close|dismiss)$/i,
        /^agree\\s*(&|and)?\\s*(close|continue|proceed)?$/i,
    ];

    const CONTAINER_RE = [
        /cookie/i, /consent/i, /gdpr/i, /cc[-_]?banner/i,
    ];

    function tryDismiss() {
        for (const sel of PLATFORM_SELECTORS) {
            try {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            } catch (_) {}
        }

        // Quick text-match fallback
        const btns = document.querySelectorAll('button, [role="button"]');
        for (const btn of btns) {
            const text = (btn.innerText || '').trim();
            if (text.length > 40) continue;
            const inContainer = (() => {
                let p = btn.parentElement, d = 0;
                while (p && d < 6) {
                    const attr = (p.id || '') + ' ' + (p.className || '');
                    if (CONTAINER_RE.some(r => r.test(attr))) return true;
                    p = p.parentElement; d++;
                }
                return false;
            })();
            if (inContainer && ACCEPT_RE.some(r => r.test(text))) {
                btn.click();
                return true;
            }
        }

        // [role="dialog"] fallback
        const dialogs = document.querySelectorAll('[role="dialog"], [role="alertdialog"]');
        for (const dialog of dialogs) {
            if (dialog.offsetParent === null) continue;
            const dialogText = (dialog.innerText || dialog.textContent || '').toLowerCase();
            if (!/cookie|consent|gdpr|privacy|tracking/.test(dialogText)) continue;
            const dBtns = dialog.querySelectorAll('button, [role="button"], a');
            for (const btn of dBtns) {
                const text = (btn.innerText || '').trim();
                if (text.length > 60) continue;
                if (ACCEPT_RE.some(r => r.test(text))) {
                    btn.click();
                    return true;
                }
            }
        }
        return false;
    }

    // Try immediately (banner may already be in DOM)
    if (tryDismiss()) return;

    // Watch for late-loading banners
    const observer = new MutationObserver((mutations, obs) => {
        if (tryDismiss()) {
            obs.disconnect();
        }
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
    });

    // Stop observing after 10 seconds to avoid leaking
    setTimeout(() => observer.disconnect(), 10000);
})();
"""


async def dismiss_cookie_consent(page) -> dict:
    """Run the cookie-consent dismissal script on *page*.

    Returns a dict like ``{"dismissed": True, "method": "platform", ...}``
    or ``{"dismissed": False}``.
    """
    try:
        result = await page.evaluate(DISMISS_COOKIE_CONSENT_JS)
        if result and result.get("dismissed"):
            logger.info(
                "Cookie consent dismissed via %s (%s)",
                result.get("method", "?"),
                result.get("selector") or result.get("text", ""),
            )
        return result or {"dismissed": False}
    except Exception as e:
        logger.debug("Cookie consent dismissal failed: %s", e)
        return {"dismissed": False, "error": str(e)}


async def install_cookie_consent_observer(context) -> None:
    """Add an init script to *context* that auto-dismisses cookie banners.

    The script is injected into every new page / navigation inside the
    context, so it catches dynamically-loaded consent managers.
    """
    try:
        await context.add_init_script(COOKIE_CONSENT_INIT_SCRIPT)
        logger.info("Cookie consent observer installed on browser context")
    except Exception as e:
        logger.debug("Failed to install cookie consent observer: %s", e)
