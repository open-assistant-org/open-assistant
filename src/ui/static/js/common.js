// Common JavaScript utilities for all pages

// API Client
class APIClient {
    constructor(baseURL = '') {
        // Use INSTANCE_BASE_PATH if defined (for managed instances under /i/{slug}/)
        this.baseURL = window.INSTANCE_BASE_PATH || baseURL;
    }

    async request(method, endpoint, data = null) {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
        };

        if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(this.baseURL + endpoint, options);

            if (!response.ok) {
                const text = await response.text();
                let detail;
                try {
                    const error = JSON.parse(text);
                    detail = error.detail;
                } catch {
                    detail = text;
                }
                const message = typeof detail === 'object' && detail !== null
                    ? JSON.stringify(detail)
                    : (detail || `HTTP ${response.status}: ${response.statusText}`);
                throw new Error(message);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error [${method} ${endpoint}]:`, error);
            throw error;
        }
    }

    async get(endpoint) {
        return this.request('GET', endpoint);
    }

    async post(endpoint, data) {
        return this.request('POST', endpoint, data);
    }

    async put(endpoint, data) {
        return this.request('PUT', endpoint, data);
    }

    async patch(endpoint, data) {
        return this.request('PATCH', endpoint, data);
    }

    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }
}

// Global API client instance
const api = new APIClient();

// Toast Notification System
class ToastManager {
    constructor() {
        this.container = this.createContainer();
    }

    createContainer() {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    show(message, type = 'info', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        this.container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('is-leaving');
            setTimeout(() => toast.remove(), 280);
        }, duration);
    }

    success(message, duration) {
        this.show(message, 'success', duration);
    }

    error(message, duration) {
        this.show(message, 'error', duration);
    }

    warning(message, duration) {
        this.show(message, 'warning', duration);
    }

    info(message, duration) {
        this.show(message, 'info', duration);
    }
}

// Global toast instance
const toast = new ToastManager();

// Modal Manager
class ModalManager {
    // buttons: [{ text, className, onClick }]. onDismiss runs when the dialog
    // closes without a button (overlay click or Escape).
    show(title, content, buttons = [], onDismiss = null) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');

        const header = document.createElement('div');
        header.className = 'modal-header';
        header.textContent = title;

        const body = document.createElement('div');
        body.className = 'modal-body';
        if (typeof content === 'string') {
            body.innerHTML = content;
        } else {
            body.appendChild(content);
        }

        const footer = document.createElement('div');
        footer.className = 'modal-footer';

        let settled = false;
        const onKey = (e) => {
            if (e.key === 'Escape') dismiss();
        };
        const finish = () => {
            settled = true;
            document.removeEventListener('keydown', onKey);
            this.close(overlay);
        };
        const dismiss = () => {
            if (settled) return;
            finish();
            if (onDismiss) onDismiss();
        };

        let lastButton = null;
        buttons.forEach(btn => {
            const button = document.createElement('button');
            button.className = `btn ${btn.className || 'btn-secondary'}`;
            if (btn.icon) {
                // Icon-only button: the text becomes the tooltip and accessible name
                button.classList.add('btn-icon');
                button.innerHTML = icon(btn.icon);
                button.title = btn.text;
                button.setAttribute('aria-label', btn.text);
            } else {
                button.textContent = btn.text;
            }
            button.onclick = () => {
                if (settled) return;
                finish();
                if (btn.onClick) btn.onClick();
            };
            footer.appendChild(button);
            lastButton = button;
        });

        modal.appendChild(header);
        modal.appendChild(body);
        modal.appendChild(footer);
        overlay.appendChild(modal);

        document.body.appendChild(overlay);
        document.addEventListener('keydown', onKey);
        if (lastButton) setTimeout(() => lastButton.focus(), 0);

        // Close on overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) dismiss();
        };

        return overlay;
    }

    close(overlay) {
        overlay.classList.add('is-leaving');
        setTimeout(() => overlay.remove(), 180);
    }

    // Callback style. options: { confirmText, cancelText, danger }
    confirm(title, message, onConfirm, options = {}) {
        const { confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = options;
        return this.show(title, message, [
            { text: cancelText, className: 'btn-secondary' },
            {
                text: confirmText,
                className: danger ? 'btn-destructive' : 'btn-primary',
                onClick: onConfirm
            }
        ]);
    }

    // Promise style, a drop-in for window.confirm():
    //   if (!await modal.ask('Delete plugin', 'This cannot be undone.', { danger: true, confirmText: 'Delete' })) return;
    // `message` is plain text; blank lines start a new paragraph.
    ask(title, message, options = {}) {
        const { confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = options;
        const content = document.createElement('div');
        String(message || '').split(/\n\s*\n/).forEach(text => {
            const p = document.createElement('p');
            p.textContent = text.trim();
            content.appendChild(p);
        });
        return new Promise(resolve => {
            this.show(title, content, [
                { text: cancelText, className: 'btn-secondary', onClick: () => resolve(false) },
                {
                    text: confirmText,
                    className: danger ? 'btn-destructive' : 'btn-primary',
                    onClick: () => resolve(true)
                }
            ], () => resolve(false));
        });
    }
}

// Global modal instance
const modal = new ModalManager();

// Navigation Helper
function setActiveNavLink() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (currentPath === '/' && href === '/')) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// Hamburger Menu
function initHamburgerMenu() {
    const hamburger = document.getElementById('navHamburger');
    const navLinks = document.querySelector('.navbar-links');
    if (!hamburger || !navLinks) return;

    hamburger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = navLinks.classList.toggle('open');
        hamburger.classList.toggle('open', isOpen);
        hamburger.setAttribute('aria-expanded', isOpen);
    });

    // Close when a nav link is clicked
    navLinks.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('open');
            hamburger.classList.remove('open');
            hamburger.setAttribute('aria-expanded', 'false');
        });
    });

    // Close when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.navbar')) {
            navLinks.classList.remove('open');
            hamburger.classList.remove('open');
            hamburger.setAttribute('aria-expanded', 'false');
        }
    });
}

// Tab Manager
function initTabs() {
    const tabs = document.querySelectorAll('.tab');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Only handle tabs that point at a panel by id. Pages with their
            // own tab logic (settings.js, monitoring) and plain segmented
            // controls (no data-tab) are left alone.
            const targetId = tab.getAttribute('data-tab');
            const target = targetId && document.getElementById(targetId);
            if (!target) return;

            const group = tab.closest('.tabs') || document;
            group.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            target.classList.add('active');
        });
    });
}

// LocalStorage Helper
const storage = {
    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (e) {
            console.error('Error reading from localStorage:', e);
            return defaultValue;
        }
    },

    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            console.error('Error writing to localStorage:', e);
        }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.error('Error removing from localStorage:', e);
        }
    }
};

// IANA timezone string set by pages that load user preferences (e.g. monitoring).
// null means fall back to the browser's local timezone.
window.userTimezone = null;

// Format an ISO timestamp as an absolute datetime in the configured user timezone.
function formatDateTimeAbsolute(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return String(isoString);
    const options = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    if (window.userTimezone) {
        options.timeZone = window.userTimezone;
        options.timeZoneName = 'short';
    }
    return date.toLocaleString(undefined, options);
}

// Format date/time — relative for recent past, absolute for older or future dates.
function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return String(isoString);

    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);

    // Future date: show absolute so the user knows exactly when
    if (seconds < 0) return formatDateTimeAbsolute(isoString);

    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return 'just now';
    if (minutes < 60) return `${minutes} min${minutes > 1 ? 's' : ''} ago`;
    if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    if (days < 7) return `${days} day${days > 1 ? 's' : ''} ago`;

    return formatDateTimeAbsolute(isoString);
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize common features on page load
document.addEventListener('DOMContentLoaded', () => {
    setActiveNavLink();
    initTabs();
    initHamburgerMenu();
});

// Export for use in other scripts
window.api = api;
window.toast = toast;
window.modal = modal;
window.storage = storage;
window.formatDateTime = formatDateTime;
window.formatDateTimeAbsolute = formatDateTimeAbsolute;
window.debounce = debounce;
