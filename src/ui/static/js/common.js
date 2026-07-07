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
            toast.style.animation = 'slideInRight 0.3s ease-out reverse';
            setTimeout(() => toast.remove(), 300);
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
    show(title, content, buttons = []) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'modal';

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

        buttons.forEach(btn => {
            const button = document.createElement('button');
            button.className = `btn ${btn.className || 'btn-secondary'}`;
            button.textContent = btn.text;
            button.onclick = () => {
                if (btn.onClick) btn.onClick();
                this.close(overlay);
            };
            footer.appendChild(button);
        });

        modal.appendChild(header);
        modal.appendChild(body);
        modal.appendChild(footer);
        overlay.appendChild(modal);

        document.body.appendChild(overlay);

        // Close on overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                this.close(overlay);
            }
        };

        return overlay;
    }

    close(overlay) {
        overlay.style.animation = 'fadeIn 0.2s reverse';
        setTimeout(() => overlay.remove(), 200);
    }

    confirm(title, message, onConfirm) {
        return this.show(title, message, [
            {
                text: 'Cancel',
                className: 'btn-secondary'
            },
            {
                text: 'Confirm',
                className: 'btn-primary',
                onClick: onConfirm
            }
        ]);
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

// Tab Manager
function initTabs() {
    const tabs = document.querySelectorAll('.tab');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.getAttribute('data-tab');

            // Remove active class from all tabs and contents
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            // Add active class to clicked tab and corresponding content
            tab.classList.add('active');
            document.getElementById(targetId).classList.add('active');
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
});

// Export for use in other scripts
window.api = api;
window.toast = toast;
window.modal = modal;
window.storage = storage;
window.formatDateTime = formatDateTime;
window.formatDateTimeAbsolute = formatDateTimeAbsolute;
window.debounce = debounce;
