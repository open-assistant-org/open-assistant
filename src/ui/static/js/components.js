// Shared page chrome: navbar and icon sprite.
//
// The app has no server-side templating (FastAPI just serves static HTML
// files — see src/main.py), so each page previously copy-pasted the navbar
// markup, which let the 4 copies drift out of sync. This module injects the
// shared chrome client-side instead: every page includes an empty
// <div id="navbar-root"></div> placeholder, and this script fills it in on
// DOMContentLoaded — before common.js's own DOMContentLoaded handler runs
// setActiveNavLink()/initHamburgerMenu() against the injected markup, as
// long as this script tag appears before common.js's in each page.

const NAV_ITEMS = [
    { href: '/', label: 'Chat', icon: 'chat' },
    { href: '/artifacts', label: 'Artifacts', icon: 'artifacts' },
    { href: '/settings', label: 'Settings', icon: 'settings' },
    { href: '/monitoring', label: 'Monitoring', icon: 'monitoring' },
];

// These links are built at runtime, so the managed platform's sub_filter
// (which only rewrites href/src/action attributes in the HTML it serves)
// can never prefix them — prefix here instead, like every other
// browser-initiated URL in the app (APIClient, PWA, service worker).
// Injected as the first element of <head> before any script runs.
const INSTANCE_BASE = window.INSTANCE_BASE_PATH || '';

// Inline SVG sprite of Lucide icons (https://lucide.dev, ISC licence),
// generated from lucide-static 0.468.0. Every icon in the UI comes from
// here - use icon('name') in JS or <svg class="icon"><use href="#icon-name">
// in HTML. Stroke width/colour are set by the .icon class in components.css
// (the symbols carry no presentation attributes, so CSS can style them).
// To add an icon: copy the inner elements of lucide-static/icons/<name>.svg
// into a new <symbol id="icon-<name>" viewBox="0 0 24 24">.
const ICON_SPRITE = `
<svg xmlns="http://www.w3.org/2000/svg" class="icon-sprite" aria-hidden="true">
    <symbol id="icon-chat" viewBox="0 0 24 24"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></symbol>
    <symbol id="icon-artifacts" viewBox="0 0 24 24"><rect width="20" height="5" x="2" y="3" rx="1"/> <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/> <path d="M10 12h4"/></symbol>
    <symbol id="icon-settings" viewBox="0 0 24 24"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/> <circle cx="12" cy="12" r="3"/></symbol>
    <symbol id="icon-monitoring" viewBox="0 0 24 24"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></symbol>
    <symbol id="icon-close" viewBox="0 0 24 24"><path d="M18 6 6 18"/> <path d="m6 6 12 12"/></symbol>
    <symbol id="icon-menu" viewBox="0 0 24 24"><line x1="4" x2="20" y1="12" y2="12"/> <line x1="4" x2="20" y1="6" y2="6"/> <line x1="4" x2="20" y1="18" y2="18"/></symbol>
    <symbol id="icon-alert" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/> <path d="M12 9v4"/> <path d="M12 17h.01"/></symbol>
    <symbol id="icon-install" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/> <polyline points="7 10 12 15 17 10"/> <line x1="12" x2="12" y1="15" y2="3"/></symbol>
    <symbol id="icon-panel-collapse" viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="3" rx="2"/> <path d="M9 3v18"/> <path d="m16 15-3-3 3-3"/></symbol>
    <symbol id="icon-panel-expand" viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="3" rx="2"/> <path d="M9 3v18"/> <path d="m14 9 3 3-3 3"/></symbol>
    <symbol id="icon-send" viewBox="0 0 24 24"><path d="m5 12 7-7 7 7"/> <path d="M12 19V5"/></symbol>
    <symbol id="icon-paperclip" viewBox="0 0 24 24"><path d="M13.234 20.252 21 12.3"/> <path d="m16 6-8.414 8.586a2 2 0 0 0 0 2.828 2 2 0 0 0 2.828 0l8.414-8.586a4 4 0 0 0 0-5.656 4 4 0 0 0-5.656 0l-8.415 8.585a6 6 0 1 0 8.486 8.486"/></symbol>
    <symbol id="icon-plus" viewBox="0 0 24 24"><path d="M5 12h14"/> <path d="M12 5v14"/></symbol>
    <symbol id="icon-stop" viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="3" rx="2"/></symbol>
    <symbol id="icon-refresh" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/> <path d="M21 3v5h-5"/> <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/> <path d="M8 16H3v5"/></symbol>
    <symbol id="icon-history" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/> <path d="M3 3v5h5"/> <path d="M12 7v5l4 2"/></symbol>
    <symbol id="icon-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
    <symbol id="icon-tool" viewBox="0 0 24 24"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></symbol>
    <symbol id="icon-lock" viewBox="0 0 24 24"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/> <path d="M7 11V7a5 5 0 0 1 10 0v4"/></symbol>
    <symbol id="icon-eye" viewBox="0 0 24 24"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/> <circle cx="12" cy="12" r="3"/></symbol>
    <symbol id="icon-trash" viewBox="0 0 24 24"><path d="M3 6h18"/> <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/> <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/> <line x1="10" x2="10" y1="11" y2="17"/> <line x1="14" x2="14" y1="11" y2="17"/></symbol>
    <symbol id="icon-chevron-down" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
    <symbol id="icon-chevron-up" viewBox="0 0 24 24"><path d="m18 15-6-6-6 6"/></symbol>
    <symbol id="icon-chevron-right" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></symbol>
    <symbol id="icon-pin" viewBox="0 0 24 24"><path d="M12 17v5"/> <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></symbol>
    <symbol id="icon-loader" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></symbol>
    <symbol id="icon-image" viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/> <circle cx="9" cy="9" r="2"/> <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></symbol>
    <symbol id="icon-file" viewBox="0 0 24 24"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/> <path d="M14 2v4a2 2 0 0 0 2 2h4"/></symbol>
    <symbol id="icon-file-text" viewBox="0 0 24 24"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/> <path d="M14 2v4a2 2 0 0 0 2 2h4"/> <path d="M10 9H8"/> <path d="M16 13H8"/> <path d="M16 17H8"/></symbol>
    <symbol id="icon-arrow-up-right" viewBox="0 0 24 24"><path d="M7 7h10v10"/> <path d="M7 17 17 7"/></symbol>
    <symbol id="icon-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/> <path d="m21 21-4.3-4.3"/></symbol>
    <symbol id="icon-circle-check" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <path d="m9 12 2 2 4-4"/></symbol>
    <symbol id="icon-circle-x" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <path d="m15 9-6 6"/> <path d="m9 9 6 6"/></symbol>
    <symbol id="icon-circle-alert" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <line x1="12" x2="12" y1="8" y2="12"/> <line x1="12" x2="12.01" y1="16" y2="16"/></symbol>
    <symbol id="icon-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <path d="M12 16v-4"/> <path d="M12 8h.01"/></symbol>
    <symbol id="icon-puzzle" viewBox="0 0 24 24"><path d="M15.39 4.39a1 1 0 0 0 1.68-.474 2.5 2.5 0 1 1 3.014 3.015 1 1 0 0 0-.474 1.68l1.683 1.682a2.414 2.414 0 0 1 0 3.414L19.61 15.39a1 1 0 0 1-1.68-.474 2.5 2.5 0 1 0-3.014 3.015 1 1 0 0 1 .474 1.68l-1.683 1.682a2.414 2.414 0 0 1-3.414 0L8.61 19.61a1 1 0 0 0-1.68.474 2.5 2.5 0 1 1-3.014-3.015 1 1 0 0 0 .474-1.68l-1.683-1.682a2.414 2.414 0 0 1 0-3.414L4.39 8.61a1 1 0 0 1 1.68.474 2.5 2.5 0 1 0 3.014-3.015 1 1 0 0 1-.474-1.68l1.683-1.682a2.414 2.414 0 0 1 3.414 0z"/></symbol>
    <symbol id="icon-plug" viewBox="0 0 24 24"><path d="M12 22v-5"/> <path d="M9 8V2"/> <path d="M15 8V2"/> <path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/></symbol>
    <symbol id="icon-server" viewBox="0 0 24 24"><rect width="20" height="8" x="2" y="2" rx="2" ry="2"/> <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/> <line x1="6" x2="6.01" y1="6" y2="6"/> <line x1="6" x2="6.01" y1="18" y2="18"/></symbol>
    <symbol id="icon-bot" viewBox="0 0 24 24"><path d="M12 8V4H8"/> <rect width="16" height="12" x="4" y="8" rx="2"/> <path d="M2 14h2"/> <path d="M20 14h2"/> <path d="M15 13v2"/> <path d="M9 13v2"/></symbol>
    <symbol id="icon-key" viewBox="0 0 24 24"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/> <circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/></symbol>
    <symbol id="icon-copy" viewBox="0 0 24 24"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/> <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></symbol>
    <symbol id="icon-link" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/> <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></symbol>
    <symbol id="icon-pencil" viewBox="0 0 24 24"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/> <path d="m15 5 4 4"/></symbol>
    <symbol id="icon-play" viewBox="0 0 24 24"><polygon points="6 3 20 12 6 21 6 3"/></symbol>
    <symbol id="icon-pause" viewBox="0 0 24 24"><rect x="14" y="4" width="4" height="16" rx="1"/> <rect x="6" y="4" width="4" height="16" rx="1"/></symbol>
    <symbol id="icon-workflow" viewBox="0 0 24 24"><rect width="8" height="8" x="3" y="3" rx="2"/> <path d="M7 11v4a2 2 0 0 0 2 2h4"/> <rect width="8" height="8" x="13" y="13" rx="2"/></symbol>
    <symbol id="icon-brain" viewBox="0 0 24 24"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/> <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/> <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/> <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/> <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/> <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/> <path d="M19.938 10.5a4 4 0 0 1 .585.396"/> <path d="M6 18a4 4 0 0 1-1.967-.516"/> <path d="M19.967 17.484A4 4 0 0 1 18 18"/></symbol>
    <symbol id="icon-timer" viewBox="0 0 24 24"><line x1="10" x2="14" y1="2" y2="2"/> <line x1="12" x2="15" y1="14" y2="11"/> <circle cx="12" cy="14" r="8"/></symbol>
    <symbol id="icon-send-message" viewBox="0 0 24 24"><path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/> <path d="m21.854 2.147-10.94 10.939"/></symbol>
    <symbol id="icon-arrow-right" viewBox="0 0 24 24"><path d="M5 12h14"/> <path d="m12 5 7 7-7 7"/></symbol>
    <symbol id="icon-corner-down-right" viewBox="0 0 24 24"><polyline points="15 10 20 15 15 20"/> <path d="M4 4v7a4 4 0 0 0 4 4h12"/></symbol>
    <symbol id="icon-arrow-down-to-line" viewBox="0 0 24 24"><path d="M12 17V3"/> <path d="m6 11 6 6 6-6"/> <path d="M19 21H5"/></symbol>
    <symbol id="icon-sparkles" viewBox="0 0 24 24"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/> <path d="M20 3v4"/> <path d="M22 5h-4"/> <path d="M4 17v2"/> <path d="M5 18H3"/></symbol>
    <symbol id="icon-smartphone" viewBox="0 0 24 24"><rect width="14" height="20" x="5" y="2" rx="2" ry="2"/> <path d="M12 18h.01"/></symbol>
    <symbol id="icon-log-in" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/> <polyline points="10 17 15 12 10 7"/> <line x1="15" x2="3" y1="12" y2="12"/></symbol>
    <symbol id="icon-save" viewBox="0 0 24 24"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/> <path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/> <path d="M7 3v4a1 1 0 0 0 1 1h7"/></symbol>
    <symbol id="icon-svc-google" viewBox="0 0 24 24"><rect width="7" height="7" x="3" y="3" rx="1"/> <rect width="7" height="7" x="14" y="3" rx="1"/> <rect width="7" height="7" x="14" y="14" rx="1"/> <rect width="7" height="7" x="3" y="14" rx="1"/></symbol>
    <symbol id="icon-svc-map" viewBox="0 0 24 24"><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/> <path d="M15 5.764v15"/> <path d="M9 3.236v15"/></symbol>
    <symbol id="icon-svc-ads" viewBox="0 0 24 24"><path d="m3 11 18-5v12L3 14v-3z"/> <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></symbol>
    <symbol id="icon-svc-mail" viewBox="0 0 24 24"><rect width="20" height="16" x="2" y="4" rx="2"/> <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></symbol>
    <symbol id="icon-svc-notion" viewBox="0 0 24 24"><path d="M13.4 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7.4"/> <path d="M2 6h4"/> <path d="M2 10h4"/> <path d="M2 14h4"/> <path d="M2 18h4"/> <path d="M21.378 5.626a1 1 0 1 0-3.004-3.004l-5.01 5.012a2 2 0 0 0-.506.854l-.837 2.87a.5.5 0 0 0 .62.62l2.87-.837a2 2 0 0 0 .854-.506z"/></symbol>
    <symbol id="icon-svc-cloud" viewBox="0 0 24 24"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></symbol>
    <symbol id="icon-svc-whatsapp" viewBox="0 0 24 24"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></symbol>
    <symbol id="icon-svc-slack" viewBox="0 0 24 24"><line x1="4" x2="20" y1="9" y2="9"/> <line x1="4" x2="20" y1="15" y2="15"/> <line x1="10" x2="8" y1="3" y2="21"/> <line x1="16" x2="14" y1="3" y2="21"/></symbol>
    <symbol id="icon-svc-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/> <path d="m21 21-4.3-4.3"/></symbol>
    <symbol id="icon-svc-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/> <path d="M2 12h20"/></symbol>
    <symbol id="icon-svc-mic" viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/> <path d="M19 10v2a7 7 0 0 1-14 0v-2"/> <line x1="12" x2="12" y1="19" y2="22"/></symbol>
    <symbol id="icon-svc-ocr" viewBox="0 0 24 24"><path d="M3 7V5a2 2 0 0 1 2-2h2"/> <path d="M17 3h2a2 2 0 0 1 2 2v2"/> <path d="M21 17v2a2 2 0 0 1-2 2h-2"/> <path d="M7 21H5a2 2 0 0 1-2-2v-2"/> <path d="M7 8h8"/> <path d="M7 12h10"/> <path d="M7 16h6"/></symbol>
    <symbol id="icon-svc-news" viewBox="0 0 24 24"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/> <path d="M18 14h-8"/> <path d="M15 18h-5"/> <path d="M10 6h8v4h-8V6Z"/></symbol>
    <symbol id="icon-svc-finance" viewBox="0 0 24 24"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/> <polyline points="16 7 22 7 22 13"/></symbol>
    <symbol id="icon-svc-system" viewBox="0 0 24 24"><rect width="16" height="16" x="4" y="4" rx="2"/> <rect width="6" height="6" x="9" y="9" rx="1"/> <path d="M15 2v2"/> <path d="M15 20v2"/> <path d="M2 15h2"/> <path d="M2 9h2"/> <path d="M20 15h2"/> <path d="M20 9h2"/> <path d="M9 2v2"/> <path d="M9 20v2"/></symbol>
    <symbol id="icon-svc-timer" viewBox="0 0 24 24"><line x1="10" x2="14" y1="2" y2="2"/> <line x1="12" x2="15" y1="14" y2="11"/> <circle cx="12" cy="14" r="8"/></symbol>
    <symbol id="icon-svc-plug" viewBox="0 0 24 24"><path d="M12 22v-5"/> <path d="M9 8V2"/> <path d="M15 8V2"/> <path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/></symbol>
    <symbol id="icon-agent-coordinator" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <circle cx="12" cy="12" r="6"/> <circle cx="12" cy="12" r="2"/></symbol>
    <symbol id="icon-agent-research" viewBox="0 0 24 24"><path d="m10.065 12.493-6.18 1.318a.934.934 0 0 1-1.108-.702l-.537-2.15a1.07 1.07 0 0 1 .691-1.265l13.504-4.44"/> <path d="m13.56 11.747 4.332-.924"/> <path d="m16 21-3.105-6.21"/> <path d="M16.485 5.94a2 2 0 0 1 1.455-2.425l1.09-.272a1 1 0 0 1 1.212.727l1.515 6.06a1 1 0 0 1-.727 1.213l-1.09.272a2 2 0 0 1-2.425-1.455z"/> <path d="m6.158 8.633 1.114 4.456"/> <path d="m8 21 3.105-6.21"/> <circle cx="12" cy="13" r="2"/></symbol>
    <symbol id="icon-agent-communication" viewBox="0 0 24 24"><rect width="20" height="16" x="2" y="4" rx="2"/> <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></symbol>
    <symbol id="icon-agent-planner" viewBox="0 0 24 24"><path d="M8 2v4"/> <path d="M16 2v4"/> <rect width="18" height="18" x="3" y="4" rx="2"/> <path d="M3 10h18"/></symbol>
    <symbol id="icon-agent-browser" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/> <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/> <path d="M2 12h20"/></symbol>
    <symbol id="icon-agent-writer" viewBox="0 0 24 24"><path d="M12 20h9"/> <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/></symbol>
    <symbol id="icon-agent-files" viewBox="0 0 24 24"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></symbol>
    <symbol id="icon-agent-system" viewBox="0 0 24 24"><path d="M20 7h-9"/> <path d="M14 17H5"/> <circle cx="17" cy="17" r="3"/> <circle cx="7" cy="7" r="3"/></symbol>
    <symbol id="icon-agent-navigator" viewBox="0 0 24 24"><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/> <circle cx="12" cy="12" r="10"/></symbol>
    <symbol id="icon-agent-default" viewBox="0 0 24 24"><path d="M12 8V4H8"/> <rect width="16" height="12" x="4" y="8" rx="2"/> <path d="M2 14h2"/> <path d="M20 14h2"/> <path d="M15 13v2"/> <path d="M9 13v2"/></symbol>
</svg>`;

const NAV_COLLAPSE_KEY = 'oa-nav-collapsed';

// Markup for a sprite icon, e.g. icon('check') or icon('chevron-down', 'expand-chevron').
function icon(name, extraClass = '') {
    return `<svg class="icon${extraClass ? ' ' + extraClass : ''}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}
window.icon = icon;

// Square trash button for every delete/remove action. Shaded red (.btn-danger)
// so it reads as destructive; `label` becomes the tooltip and accessible name.
//   trashButton("deleteAgent('x')", 'Remove agent')
//   trashButton("deleteRow(1)", 'Delete', 'job-action-btn')   // inside tables
function trashButton(onclick, label = 'Delete', classes = 'btn btn-danger btn-sm btn-icon') {
    const safe = String(label).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const cls = classes === 'job-action-btn' ? 'job-action-btn btn-danger job-action-icon' : classes;
    return `<button type="button" class="${cls}" onclick="${onclick}" title="${safe}" aria-label="${safe}">${icon('trash')}</button>`;
}
window.trashButton = trashButton;

// Badge classes for a job/run status. Only outcomes get colour (see
// docs/design-system.md): success and failure are tinted, everything
// in between (pending, running, cancelled, skipped) stays neutral.
const STATUS_BADGE_TONES = {
    success: 'success',
    completed: 'success',
    failed: 'danger',
    error: 'danger',
};
function statusBadgeClass(status) {
    return `badge badge-${STATUS_BADGE_TONES[status] || 'neutral'}`;
}
window.statusBadgeClass = statusBadgeClass;

// Brand mark: a rounded tile in the accent colour with a simple, friendly
// face. Drawn with currentColor/var() so it follows the theme and any
// future installation accent (--brand) automatically.
const LOGO_MARK = `
<svg class="navbar-logo" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="9" fill="var(--color-accent)"></rect>
    <circle cx="11.5" cy="13.5" r="2" fill="var(--color-on-accent)"></circle>
    <circle cx="20.5" cy="13.5" r="2" fill="var(--color-on-accent)"></circle>
    <path d="M10.5 19.5c1.4 1.9 3.3 2.8 5.5 2.8s4.1-.9 5.5-2.8" fill="none" stroke="var(--color-on-accent)" stroke-width="2.2" stroke-linecap="round"></path>
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
        <a href="${INSTANCE_BASE}${item.href}" class="nav-link" title="${item.label}">
            <svg class="nav-link-icon" aria-hidden="true"><use href="#icon-${item.icon}"></use></svg>
            <span class="nav-link-label">${item.label}</span>
        </a>`).join('');

    // Collapsed by default — an explicit '0' is the only way to get the
    // expanded rail, so a first-time visitor (or one with storage blocked)
    // sees the compact icon-only sidebar.
    let collapsed = true;
    try {
        collapsed = localStorage.getItem(NAV_COLLAPSE_KEY) !== '0';
    } catch (e) {
        // localStorage unavailable (private browsing, blocked storage) — default to collapsed.
    }

    root.outerHTML = `
    <nav class="navbar${collapsed ? ' collapsed' : ''}">
        <div class="navbar-content">
            <a href="${INSTANCE_BASE}/" class="navbar-brand" aria-label="Open Assistant home">
                ${LOGO_MARK}
                <span class="navbar-brand-name">Open Assistant</span>
            </a>
            <div class="navbar-links">${links}</div>
            <button class="navbar-hamburger" id="navHamburger" aria-label="Toggle navigation" aria-expanded="false">
                ${icon('menu', 'navbar-hamburger-open')}
                ${icon('close', 'navbar-hamburger-close')}
            </button>
            <button class="navbar-collapse-btn" id="navCollapseBtn" title="${collapsed ? 'Expand sidebar' : 'Collapse sidebar'}" aria-label="Toggle sidebar width">
                <svg class="icon navbar-collapse-icon" aria-hidden="true"><use href="#icon-panel-collapse"></use></svg>
                <svg class="icon navbar-expand-icon" aria-hidden="true"><use href="#icon-panel-expand"></use></svg>
                <span class="nav-link-label">Collapse</span>
            </button>
        </div>
    </nav>`;

    initNavbarCollapse();
}

// Desktop-only fold-in/out for the sidebar rail. Persisted in
// localStorage so it stays put across the full-page navigations this
// (framework-free, multi-page) app does between Chat/Artifacts/Settings/
// Monitoring.
function initNavbarCollapse() {
    const btn = document.getElementById('navCollapseBtn');
    const navbar = document.querySelector('.navbar');
    if (!btn || !navbar) return;

    btn.addEventListener('click', () => {
        const collapsed = navbar.classList.toggle('collapsed');
        btn.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
        try {
            localStorage.setItem(NAV_COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (e) {
            // Ignore — collapse state just won't persist this session.
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    injectIconSprite();
    renderNavbar();
});
