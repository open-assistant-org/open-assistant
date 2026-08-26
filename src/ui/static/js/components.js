// Shared page chrome: navbar, footer, and icon sprite.
//
// The app has no server-side templating (FastAPI just serves static HTML
// files — see src/main.py), so each page previously copy-pasted the navbar
// markup, which let the 4 copies drift out of sync. This module injects the
// shared chrome client-side instead: every page includes an empty
// <div id="navbar-root"></div> (and, where appropriate, a
// <div id="footer-root"></div>) placeholder, and this script fills them in
// on DOMContentLoaded — before common.js's own DOMContentLoaded handler
// runs setActiveNavLink()/initHamburgerMenu() against the injected markup,
// as long as this script tag appears before common.js's in each page.

const NAV_ITEMS = [
    { href: '/', label: 'Chat', icon: 'chat' },
    { href: '/artifacts', label: 'Artifacts', icon: 'artifacts' },
    { href: '/settings', label: 'Settings', icon: 'settings' },
    { href: '/monitoring', label: 'Monitoring', icon: 'monitoring' },
];

// A single inline SVG sprite sheet covering the small, fixed set of system
// icons used across the app (nav, controls, status) — in place of the
// previous mix of raw inline SVG, Unicode symbols, and emoji standing in
// for icons.
const ICON_SPRITE = `
<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true">
    <symbol id="icon-chat" viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
    <symbol id="icon-artifacts" viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M1 3h22v5H1z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><line x1="10" y1="13" x2="14" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
    <symbol id="icon-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82A1.65 1.65 0 0 0 3 13.09H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
    <symbol id="icon-monitoring" viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
    <symbol id="icon-close" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
    <symbol id="icon-menu" viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="12" x2="21" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="18" x2="21" y2="18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
    <symbol id="icon-alert" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="9" x2="12" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="17" x2="12.01" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
</svg>`;

function injectIconSprite() {
    if (document.getElementById('oa-icon-sprite')) return;
    const wrapper = document.createElement('div');
    wrapper.id = 'oa-icon-sprite';
    wrapper.innerHTML = ICON_SPRITE;
    document.body.prepend(wrapper);
}

function renderNavbar() {
    const root = document.getElementById('navbar-root');
    if (!root) return;

    const links = NAV_ITEMS.map(item => `
        <a href="${item.href}" class="nav-link">
            <svg class="nav-link-icon" aria-hidden="true"><use href="#icon-${item.icon}"></use></svg>
            <span>${item.label}</span>
        </a>`).join('');

    root.outerHTML = `
    <nav class="navbar">
        <div class="navbar-content">
            <a href="/" class="navbar-brand" aria-label="Open Assistant home">
                <img src="/static/robot-logo.svg" alt="" class="navbar-logo">
                <span>Open Assistant</span>
                <span class="navbar-brand-short">OA</span>
            </a>
            <div class="navbar-links">${links}</div>
            <button class="navbar-hamburger" id="navHamburger" aria-label="Toggle navigation" aria-expanded="false">
                <span></span>
                <span></span>
                <span></span>
            </button>
        </div>
    </nav>`;
}

function renderFooter() {
    const root = document.getElementById('footer-root');
    if (!root) return;

    const year = new Date().getFullYear();
    root.outerHTML = `
    <footer class="site-footer">
        <span>&copy; ${year} Open Assistant</span>
        <a href="https://github.com/open-assistant-org/open-assistant" target="_blank" rel="noopener noreferrer">GitHub</a>
    </footer>`;
}

document.addEventListener('DOMContentLoaded', () => {
    injectIconSprite();
    renderNavbar();
    renderFooter();
});
