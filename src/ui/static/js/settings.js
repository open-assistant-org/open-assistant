/**
 * Settings Page JavaScript
 * Handles all settings UI interactions, validation, and API calls
 */

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

const settingsState = {
    definitions: {},
    currentValues: {},
    categories: {},
    currentIntegration: null,
    migrationResults: null,
    connectionStatuses: {},
    integrations: {},
    integrationsLoaded: false,
    agents: [],
    agentsLoaded: false,
    availableTools: [],
    currentAgent: null,
    promptsLoaded: false,
    prompts: {},
    toolsLoaded: false,
    toolsGrouped: {},
    toolsAgentList: [],
    pendingToolAssignments: {},
    managedStatus: null,
    pluginsLoaded: false
};

// ============================================================================
// INITIALIZATION
// ============================================================================

async function initializeSettings() {
    try {
        // Load setting definitions
        await loadDefinitions();

        // Load managed status (for managed instances, certain fields/services are hidden)
        await loadManagedStatus();

        // Setup tab switching
        setupTabs();

        // Hide tabs that are not available in managed mode
        hideManagedTabs();

        // Load categories that are always visible
        await loadCategory('logging');
        await loadCategory('memory');
        await loadCategory('web_ui');
        await loadCategory('user');

        // Only load LLM and Application tabs if not managed
        if (!settingsState.managedStatus || !settingsState.managedStatus.is_managed) {
            await loadCategory('application');
            await loadCategory('llm');
        }

        // Don't load integrations immediately - lazy load when tab is opened
        // This speeds up initial page load
        settingsState.integrationsLoaded = false;

        // Load agents for the default active tab
        await loadAgents();
        settingsState.agentsLoaded = true;

        // Load audit log
        await loadAuditLog();

    } catch (error) {
        console.error('Failed to initialize settings:', error);
        toast.error('Failed to load settings');
    }
}

async function loadDefinitions() {
    try {
        const response = await api.get('/api/settings/definitions');
        response.definitions.forEach(def => {
            settingsState.definitions[def.key] = def;
        });
    } catch (error) {
        console.error('Failed to load definitions:', error);
        throw error;
    }
}

async function loadManagedStatus() {
    try {
        const response = await api.get('/api/settings/managed-status');
        settingsState.managedStatus = response;
    } catch (error) {
        console.error('Failed to load managed status:', error);
        // Default to not managed if the endpoint fails
        settingsState.managedStatus = {
            is_managed: false,
            hidden_services: [],
            managed_fields: {}
        };
    }
}

function hideManagedTabs() {
    if (!settingsState.managedStatus || !settingsState.managedStatus.is_managed) {
        return;
    }

    // Hide LLM and Application tabs in managed mode (Advanced is always visible)
    const tabsToHide = ['llm', 'application'];
    tabsToHide.forEach(tabName => {
        const tab = document.querySelector(`.tab[data-tab="${tabName}"]`);
        if (tab) {
            tab.style.display = 'none';
        }
        const tabContent = document.getElementById(`${tabName}-tab`);
        if (tabContent) {
            tabContent.style.display = 'none';
        }
    });
}

// ============================================================================
// TAB MANAGEMENT
// ============================================================================

function setupTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            await switchTab(tab.dataset.tab);
        });
    });
}

async function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Lazy load prompts when tab is first opened
    if (tabName === 'prompts' && !settingsState.promptsLoaded) {
        try {
            await loadPrompts();
            settingsState.promptsLoaded = true;
        } catch (error) {
            console.error('Failed to load prompts:', error);
            toast.error('Failed to load prompts');
        }
    }

    // Lazy load integrations when tab is first opened
    if (tabName === 'integrations' && !settingsState.integrationsLoaded) {
        try {
            await loadIntegrations();
            settingsState.integrationsLoaded = true;
        } catch (error) {
            console.error('Failed to load integrations:', error);
            toast.error('Failed to load integrations');
        }
    }

    // Lazy load agents when tab is first opened
    if (tabName === 'agents' && !settingsState.agentsLoaded) {
        try {
            await loadAgents();
            settingsState.agentsLoaded = true;
        } catch (error) {
            console.error('Failed to load agents:', error);
            toast.error('Failed to load agents');
        }
    }

    // Lazy load tools when tab is first opened
    if (tabName === 'tools' && !settingsState.toolsLoaded) {
        try {
            await loadToolsGrouped();
            settingsState.toolsLoaded = true;
        } catch (error) {
            console.error('Failed to load tools:', error);
            toast.error('Failed to load tools');
        }
    }

    // Lazy load plugins when tab is first opened
    if (tabName === 'plugins' && !settingsState.pluginsLoaded) {
        try {
            await loadPlugins();
            settingsState.pluginsLoaded = true;
        } catch (error) {
            console.error('Failed to load plugins:', error);
            toast.error('Failed to load plugins');
        }
    }
}

// ============================================================================
// CATEGORY LOADING
// ============================================================================

async function loadCategory(category) {
    try {
        const response = await api.get(`/api/settings/category/${category}`);
        settingsState.categories[category] = response.settings;

        // Render settings based on category
        if (category === 'application') {
            // Application category contains general application settings
            document.getElementById('application-general-settings').innerHTML = renderSettingsFields(response.settings);
        } else if (category === 'logging') {
            // Logging category
            document.getElementById('logging-settings').innerHTML = renderSettingsFields(response.settings);
        } else if (category === 'memory') {
            // Memory category
            document.getElementById('memory-settings').innerHTML = renderSettingsFields(response.settings);
        } else if (category === 'web_ui') {
            // Web UI category
            document.getElementById('web-ui-settings').innerHTML = renderSettingsFields(response.settings);
        } else if (category === 'llm') {
            // LLM category
            document.getElementById('llm-settings').innerHTML = renderSettingsFields(response.settings);
        } else if (category === 'user') {
            // User preferences category (rendered in Advanced tab)
            document.getElementById('user-preferences-settings').innerHTML = renderSettingsFields(response.settings);
        }

    } catch (error) {
        console.error(`Failed to load ${category} settings:`, error);
        toast.error(`Failed to load ${category} settings`);
    }
}

// ============================================================================
// SETTINGS RENDERING
// ============================================================================

function renderApplicationSettings(settings) {
    // Group by sub-category
    const general = settings.filter(s => s.definition.category === 'application');
    const logging = settings.filter(s => s.definition.category === 'logging');
    const memory = settings.filter(s => s.definition.category === 'memory');
    const webUI = settings.filter(s => s.definition.category === 'web_ui');

    if (general.length) {
        document.getElementById('application-general-settings').innerHTML = renderSettingsFields(general);
    }
    if (logging.length) {
        document.getElementById('logging-settings').innerHTML = renderSettingsFields(logging);
    }
    if (memory.length) {
        document.getElementById('memory-settings').innerHTML = renderSettingsFields(memory);
    }
    if (webUI.length) {
        document.getElementById('web-ui-settings').innerHTML = renderSettingsFields(webUI);
    }
}

function renderLLMSettings(settings) {
    document.getElementById('llm-settings').innerHTML = renderSettingsFields(settings);
}

function renderLoggingSettings(settings) {
    document.getElementById('logging-settings').innerHTML = renderSettingsFields(settings);
}

function renderMemorySettings(settings) {
    document.getElementById('memory-settings').innerHTML = renderSettingsFields(settings);
}

function renderWebUISettings(settings) {
    document.getElementById('web-ui-settings').innerHTML = renderSettingsFields(settings);
}

function renderSettingsFields(settings) {
    return settings.map(setting => renderField(setting)).join('');
}

function renderField(setting) {
    const def = setting.definition;
    const value = setting.value;
    const source = setting.source;

    // Store current value
    settingsState.currentValues[def.key] = value;

    const sourceBadge = `<span class="setting-source source-${source}">${source.toUpperCase()}</span>`;

    let fieldHtml = '';

    switch (def.ui_widget) {
        case 'text':
        case 'masked':
            fieldHtml = renderTextInput(def, value);
            break;
        case 'number':
            fieldHtml = renderNumberInput(def, value);
            break;
        case 'select':
            fieldHtml = renderSelect(def, value);
            break;
        case 'toggle':
            fieldHtml = renderToggle(def, value);
            break;
        case 'slider':
            fieldHtml = renderSlider(def, value);
            break;
        case 'textarea':
            fieldHtml = renderTextarea(def, value);
            break;
        default:
            fieldHtml = renderTextInput(def, value);
    }

    return `
        <div class="form-group">
            <div class="setting-header">
                <label class="form-label" for="${def.key}">
                    ${def.display_name}
                    ${def.is_required ? '<span class="required">*</span>' : ''}
                </label>
                ${sourceBadge}
            </div>
            ${fieldHtml}
            ${def.description ? `<small class="form-hint">${def.description}</small>` : ''}
            ${def.help_url ? `<a href="${def.help_url}" target="_blank" class="help-link">Learn more</a>` : ''}
        </div>
    `;
}

function renderTextInput(def, value) {
    const isMasked = def.ui_widget === 'masked' || def.is_sensitive;
    const inputType = isMasked ? 'password' : 'text';
    const displayValue = def.is_sensitive && value ? '***MASKED***' : value;

    return `
        <div class="input-group">
            <input
                type="${inputType}"
                id="${def.key}"
                class="form-input ${isMasked ? 'masked-input' : ''}"
                value="${displayValue || ''}"
                placeholder="${def.placeholder || ''}"
                ${def.is_required ? 'required' : ''}
                data-original-value="${value || ''}"
            >
            ${isMasked ? `<button type="button" class="btn-icon" onclick="toggleMasked('${def.key}')">👁️</button>` : ''}
        </div>
    `;
}

function renderNumberInput(def, value) {
    return `
        <input
            type="number"
            id="${def.key}"
            class="form-input"
            value="${value || def.default_value || ''}"
            placeholder="${def.placeholder || ''}"
            ${def.min_value !== null ? `min="${def.min_value}"` : ''}
            ${def.max_value !== null ? `max="${def.max_value}"` : ''}
            ${def.is_required ? 'required' : ''}
        >
    `;
}

function renderSelect(def, value) {
    const options = def.options || [];
    return `
        <select id="${def.key}" class="form-select" ${def.is_required ? 'required' : ''}>
            ${options.map(opt => `
                <option value="${opt}" ${value === opt ? 'selected' : ''}>${opt}</option>
            `).join('')}
        </select>
    `;
}

function renderToggle(def, value) {
    const checked = value === true || value === 'true';
    return `
        <label class="toggle-label">
            <input
                type="checkbox"
                id="${def.key}"
                class="toggle-input"
                ${checked ? 'checked' : ''}
            >
            <span class="toggle-slider"></span>
            <span class="toggle-text">${checked ? 'Enabled' : 'Disabled'}</span>
        </label>
    `;
}

function renderSlider(def, value) {
    return `
        <div class="slider-group">
            <input
                type="range"
                id="${def.key}"
                class="form-slider"
                value="${value || def.default_value || 0}"
                min="${def.min_value || 0}"
                max="${def.max_value || 1}"
                step="0.1"
                oninput="updateSliderValue('${def.key}')"
            >
            <span id="${def.key}-value" class="slider-value">${value || def.default_value || 0}</span>
        </div>
    `;
}

function renderTextarea(def, value) {
    return `
        <textarea
            id="${def.key}"
            class="form-textarea"
            placeholder="${def.placeholder || ''}"
            ${def.is_required ? 'required' : ''}
            rows="4"
        >${value || ''}</textarea>
    `;
}

// ============================================================================
// FIELD INTERACTIONS
// ============================================================================

function toggleMasked(key) {
    const input = document.getElementById(key);
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
}

function updateSliderValue(key) {
    const slider = document.getElementById(key);
    const valueDisplay = document.getElementById(`${key}-value`);
    valueDisplay.textContent = slider.value;
}

// ============================================================================
// SAVING SETTINGS
// ============================================================================

// Collect the changed values from a single category's rendered fields.
function collectCategoryUpdates(category) {
    const updates = {};
    const settings = settingsState.categories[category];
    if (!settings) {
        return updates;
    }

    for (const setting of settings) {
        const key = setting.definition.key;
        const element = document.getElementById(key);

        if (!element) continue;

        let value;
        if (setting.definition.ui_widget === 'toggle') {
            value = element.checked;
        } else if (setting.definition.value_type === 'int') {
            value = parseInt(element.value);
        } else if (setting.definition.value_type === 'float') {
            value = parseFloat(element.value);
        } else {
            value = element.value;
        }

        // Skip if value hasn't changed (unless it's masked)
        if (!setting.definition.is_sensitive && value === settingsState.currentValues[key]) {
            continue;
        }

        // Skip masked inputs that haven't been changed
        if (setting.definition.is_sensitive && value === '***MASKED***') {
            continue;
        }

        updates[key] = value;
    }

    return updates;
}

async function saveCategory(category) {
    return saveCategories([category], category);
}

// Save one or more categories rendered together under a single tab/button.
// A tab like Application renders several categories (application, logging,
// memory, web_ui) but has one Save button, so all of them must be collected
// into a single bulk update — otherwise sibling sections silently don't save.
async function saveCategories(categories, label) {
    try {
        const known = categories.filter(c => settingsState.categories[c]);
        if (known.length === 0) {
            toast.error('No settings to save');
            return;
        }

        let updates = {};
        for (const category of known) {
            updates = { ...updates, ...collectCategoryUpdates(category) };
        }

        if (Object.keys(updates).length === 0) {
            toast.info('No changes to save');
            return;
        }

        // Save via bulk update (the endpoint accepts keys from any category)
        await api.post('/api/settings/bulk-update', { settings: updates });

        toast.success(`${label || known.join(', ')} settings saved successfully`);

        // Reload the affected categories to show updated values
        for (const category of known) {
            await loadCategory(category);
        }

    } catch (error) {
        console.error('Failed to save settings:', error);
        toast.error('Failed to save settings: ' + error.message);
    }
}

// The Application tab renders the application, logging, memory and web_ui
// categories together under one Save button.
async function saveApplicationSettings() {
    return saveCategories(['application', 'logging', 'memory', 'web_ui'], 'Application');
}

// ============================================================================
// INTEGRATIONS
// ============================================================================

async function loadIntegrations() {
    try {
        let services = ['google', 'google_navigator', 'outlook', 'notion', 'nextcloud', 'whatsapp', 'slack', 'brave', 'browser', 'whisper', 'mistral_ocr', 'google_ads', 'google_news', 'yahoo_finance'];
        const container = document.getElementById('integrations-list');

        // Filter out hidden services for managed instances
        if (settingsState.managedStatus && settingsState.managedStatus.is_managed) {
            const hiddenServices = settingsState.managedStatus.hidden_services || [];
            services = services.filter(s => !hiddenServices.includes(s));
        }

        container.innerHTML = '';

        const cards = await Promise.all(services.map(service => createIntegrationCard(service)));
        cards.forEach(card => container.appendChild(card));

    } catch (error) {
        console.error('Failed to load integrations:', error);
        toast.error('Failed to load integrations');
    }
}

async function createIntegrationCard(serviceName) {
    try {
        // Use category endpoint instead of custom integrations endpoint
        const response = await api.get(`/api/settings/category/${serviceName}`);

        // Extract enabled setting from the settings list
        const enabledSetting = response.settings.find(s => s.key === `${serviceName}.enabled`);
        const isEnabled = enabledSetting ? enabledSetting.value : false;

        // Store settings data for later use
        settingsState.integrations = settingsState.integrations || {};
        settingsState.integrations[serviceName] = response.settings;

        // Check if this service has hidden fields in managed mode
        const isManaged = settingsState.managedStatus && settingsState.managedStatus.is_managed;
        const managedFields = isManaged ? (settingsState.managedStatus.managed_fields[serviceName] || []) : [];

        const card = document.createElement('div');
        card.className = 'integration-card';
        card.id = `integration-${serviceName}`;

        // Filter out fields that are hidden in managed mode
        const settingsHtml = response.settings
            .filter(s => !s.key.endsWith('.enabled')) // Don't show enabled toggle twice
            .filter(s => !managedFields.includes(s.key)) // Filter managed fields
            .map(setting => renderField(setting))
            .join('');

        const docUrl = getIntegrationDocUrl(serviceName);

        // Determine if this is an OAuth service
        const isOAuthService = serviceName === 'google' || serviceName === 'outlook' || serviceName === 'google_ads';

        // Build action buttons HTML
        // In managed mode, some services only get Test Connection button (no Save Settings)
        const isManagedOnlyService = isManaged && ['google_navigator', 'brave', 'whisper', 'mistral_ocr'].includes(serviceName);
        // Services that need no configuration beyond the enable toggle (no credentials, no settings)
        const isNoConfigService = serviceName === 'yahoo_finance';

        let actionButtonsHtml = '';
        if (isOAuthService) {
            const authFunctionName = serviceName === 'google' ? 'authenticateGoogle' :
                                     serviceName === 'google_ads' ? 'authenticateGoogleAds' :
                                     'authenticateOutlook';
            actionButtonsHtml = `
                <button onclick="${authFunctionName}()" class="btn btn-primary">
                    🔐 Authenticate ${serviceName.charAt(0).toUpperCase() + serviceName.slice(1)}
                </button>
                <button onclick="testConnection('${serviceName}')" class="btn btn-secondary">
                    🔍 Test Connection
                </button>
                ${(!isManaged || managedFields.length === 0) ? `<button onclick="saveIntegration('${serviceName}')" class="btn btn-primary">
                    💾 Save Settings
                </button>` : ''}
            `;
        } else if (serviceName === 'whatsapp') {
            actionButtonsHtml = `
                <button onclick="linkWhatsApp()" class="btn btn-primary">
                    📱 Link WhatsApp
                </button>
                <button onclick="testConnection('${serviceName}')" class="btn btn-secondary">
                    🔍 Test Connection
                </button>
                <button onclick="saveIntegration('${serviceName}')" class="btn btn-primary">
                    💾 Save Settings
                </button>
            `;
        } else if (isNoConfigService) {
            actionButtonsHtml = `
                <button onclick="testConnection('${serviceName}')" class="btn btn-secondary">
                    🔍 Test Connection
                </button>
            `;
        } else {
            actionButtonsHtml = `
                <button onclick="testConnection('${serviceName}')" class="btn btn-secondary">
                    🔍 Test Connection
                </button>
                ${!isManagedOnlyService ? `<button onclick="saveIntegration('${serviceName}')" class="btn btn-primary">
                    💾 Save Settings
                </button>` : ''}
            `;
        }

        card.innerHTML = `
            <div class="integration-header" onclick="toggleIntegrationExpanded('${serviceName}')">
                <div class="integration-title">
                    <span class="integration-icon">${getServiceIcon(serviceName)}</span>
                    <h4>${getServiceDisplayName(serviceName)}</h4>
                    <span class="expand-icon">▼</span>
                </div>
                <label class="toggle-label" onclick="event.stopPropagation()">
                    <input
                        type="checkbox"
                        class="toggle-input"
                        ${isEnabled ? 'checked' : ''}
                        onchange="toggleIntegration('${serviceName}', this.checked)"
                    >
                    <span class="toggle-slider"></span>
                </label>
            </div>
            <div class="integration-body" style="display: none;">
                ${(!isManaged || managedFields.length === 0) && !isNoConfigService ? `<div class="integration-help">
                    <a href="${docUrl}" target="_blank" class="help-link">
                        📚 How to get ${serviceName} credentials?
                    </a>
                </div>` : ''}
                <div class="integration-settings">
                    ${settingsHtml}
                </div>
                <div class="integration-actions">
                    ${actionButtonsHtml}
                </div>
            </div>
        `;

        return card;

    } catch (error) {
        console.error(`Failed to load ${serviceName} integration:`, error);
        const card = document.createElement('div');
        card.className = 'integration-card error';
        card.innerHTML = `
            <div class="integration-header">
                <div class="integration-title">
                    <span class="integration-icon">⚠️</span>
                    <h4>${getServiceDisplayName(serviceName)}</h4>
                </div>
            </div>
            <div class="integration-body">
                <p class="error-text">Failed to load integration settings</p>
            </div>
        `;
        return card;
    }
}

function getServiceIcon(service) {
    const icons = {
        google: '🔵',
        google_navigator: '🗺️',
        google_ads: '📊',
        outlook: '📨',
        notion: '📝',
        nextcloud: '☁️',
        whatsapp: '💬',
        slack: '📢',
        brave: '🔎',
        browser: '🌐',
        whisper: '🎙️',
        mistral_ocr: '🔍',
        toggl: '⏱️',
        google_news: '📰',
        yahoo_finance: '📈'
    };
    return icons[service] || '🔧';
}

function getServiceDisplayName(service) {
    const names = {
        google: 'Google',
        google_navigator: 'Google Navigator',
        google_ads: 'Google Ads',
        outlook: 'Outlook',
        notion: 'Notion',
        nextcloud: 'Nextcloud',
        whatsapp: 'WhatsApp',
        slack: 'Slack',
        brave: 'Brave',
        browser: 'Browser',
        whisper: 'Whisper',
        mistral_ocr: 'Mistral OCR',
        toggl: 'Toggl',
        google_news: 'Google News',
        yahoo_finance: 'Yahoo Finance'
    };
    return names[service] || service.charAt(0).toUpperCase() + service.slice(1);
}

function getIntegrationDocUrl(service) {
    const docMap = {
        google: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google.md',
        google_navigator: 'https://developers.google.com/maps/documentation/places/web-service/get-api-key',
        google_ads: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_ads.md',
        outlook: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/microsoft.md',
        notion: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/notion.md',
        nextcloud: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/nextcloud.md',
        whatsapp: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/whatsapp.md',
        slack: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/slack.md',
        brave: 'https://brave.com/search/api/',
        browser: 'https://playwright.dev/',
        whisper: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/whisper.md',
        mistral_ocr: 'https://docs.mistral.ai/capabilities/vision/',
        toggl: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/toggl.md',
        google_news: 'https://github.com/open-assistant-org/open-assistant/blob/main/docs/integrations/google_news.md'
    };
    return docMap[service] || '#';
}

function renderConnectionStatus(hasCredentials, service) {
    if (hasCredentials) {
        return '<span class="status-badge status-success">Connected</span>';
    } else {
        return '<span class="status-badge status-warning">Not Configured</span>';
    }
}

async function toggleIntegration(service, enabled) {
    try {
        // Update the enabled setting for this integration
        const key = `${service}.enabled`;
        const result = await api.put(`/api/settings/${key}`, {
            value: enabled,
            value_type: 'bool'
        });
        toast.success(`${getServiceDisplayName(service)} ${enabled ? 'enabled' : 'disabled'}`);
    } catch (error) {
        console.error('Failed to toggle integration:', error);
        toast.error('Failed to update integration');
    }
}

function toggleIntegrationExpanded(service) {
    const card = document.getElementById(`integration-${service}`);
    const body = card.querySelector('.integration-body');
    const icon = card.querySelector('.expand-icon');

    if (body.style.display === 'none') {
        body.style.display = 'block';
        icon.textContent = '▲';
    } else {
        body.style.display = 'none';
        icon.textContent = '▼';
    }
}

async function saveIntegration(service) {
    try {
        const settings = settingsState.integrations[service];
        if (!settings) {
            toast.error('No settings to save');
            return;
        }

        // Collect values from form fields
        const updates = {};
        for (const setting of settings) {
            const element = document.getElementById(setting.key);
            if (element) {
                let value;
                if (element.type === 'checkbox') {
                    value = element.checked;
                } else if (element.type === 'number' || element.type === 'range') {
                    value = parseFloat(element.value);
                } else {
                    value = element.value;
                }

                // Skip masked inputs that haven't been changed
                if (setting.definition && setting.definition.is_sensitive && value === '***MASKED***') {
                    continue;
                }

                updates[setting.key] = value;
            }
        }

        // Save each setting
        let successCount = 0;
        for (const [key, value] of Object.entries(updates)) {
            try {
                const setting = settings.find(s => s.key === key);
                await api.put(`/api/settings/${key}`, {
                    value: value,
                    value_type: setting.definition.value_type
                });
                successCount++;
            } catch (error) {
                console.error(`Failed to save ${key}:`, error);
            }
        }

        if (successCount > 0) {
            toast.success(`Saved ${successCount} ${getServiceDisplayName(service)} settings`);
        } else if (Object.keys(updates).length === 0) {
            toast.info('No changes to save');
        } else {
            toast.error('Failed to save settings');
        }

    } catch (error) {
        console.error('Failed to save integration:', error);
        toast.error('Failed to save settings');
    }
}

async function saveIntegrationSettings() {
    const service = settingsState.currentIntegration;
    if (!service) return;

    try {
        const settings = settingsState.categories[service];
        const updates = {};

        for (const setting of settings) {
            const key = setting.definition.key;
            const element = document.getElementById(key);
            if (element) {
                updates[key] = element.value;
            }
        }

        await api.post('/api/settings/bulk-update', { settings: updates });
        toast.success('Settings saved');
        closeIntegrationModal();

    } catch (error) {
        console.error('Failed to save integration settings:', error);
        toast.error('Failed to save settings');
    }
}

function closeIntegrationModal() {
    document.getElementById('integrationModal').style.display = 'none';
    settingsState.currentIntegration = null;
}

async function testIntegration(service) {
    try {
        const response = await api.post(`/api/settings/credentials/${service}/test`);

        if (response.status === 'connected') {
            toast.success(`${service} connection successful`);
        } else {
            toast.error(`${service} connection failed: ${response.message}`);
        }
    } catch (error) {
        console.error('Connection test failed:', error);
        toast.error('Connection test failed');
    }
}

// ============================================================================
// PROMPTS
// ============================================================================

async function loadPrompts() {
    try {
        const response = await api.get('/api/prompts');
        settingsState.prompts = {};

        for (const prompt of response.prompts) {
            settingsState.prompts[prompt.key] = prompt;
            const textarea = document.getElementById(`prompt-${prompt.key}`);
            if (textarea) {
                textarea.value = prompt.value || '';
            }
        }
    } catch (error) {
        console.error('Failed to load prompts:', error);
        toast.error('Failed to load prompts');
    }
}

async function savePrompts() {
    try {
        const keys = ['system_prompt_default', 'system_prompt_custom', 'memory', 'soul'];
        let successCount = 0;

        for (const key of keys) {
            const textarea = document.getElementById(`prompt-${key}`);
            if (!textarea) continue;

            const newValue = textarea.value;
            const currentPrompt = settingsState.prompts[key];

            // Skip if value hasn't changed
            if (currentPrompt && currentPrompt.value === newValue) {
                continue;
            }

            try {
                await api.put(`/api/prompts/${key}`, { value: newValue });
                successCount++;

                // Update local state
                if (settingsState.prompts[key]) {
                    settingsState.prompts[key].value = newValue;
                }
            } catch (error) {
                console.error(`Failed to save prompt ${key}:`, error);
                toast.error(`Failed to save ${key}`);
            }
        }

        if (successCount > 0) {
            toast.success('Prompts saved successfully');
        } else {
            toast.info('No changes to save');
        }
    } catch (error) {
        console.error('Failed to save prompts:', error);
        toast.error('Failed to save prompts');
    }
}

// ============================================================================
// LLM CONNECTION TEST
// ============================================================================

async function testLLMConnection() {
    try {
        const resultDiv = document.getElementById('llm-test-result');
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<p>Testing connection...</p>';

        const response = await api.post('/api/settings/test-llm');

        if (response.status === 'connected') {
            resultDiv.innerHTML = `<p class="success">✅ Connection successful!</p>`;
        } else if (response.status === 'error') {
            resultDiv.innerHTML = `<p class="error">❌ ${response.message}</p>`;
        } else {
            resultDiv.innerHTML = `<p class="warning">⚠️ ${response.message}</p>`;
        }

    } catch (error) {
        const resultDiv = document.getElementById('llm-test-result');
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `<p class="error">❌ Test failed: ${error.message}</p>`;
    }
}

// ============================================================================
// AUDIT LOG
// ============================================================================

async function loadAuditLog() {
    try {
        const eventType = document.getElementById('audit-event-type')?.value || '';
        const params = new URLSearchParams();

        if (eventType) {
            params.append('event_type', eventType);
        }
        params.append('limit', '50');

        const response = await api.get(`/api/settings/audit?${params}`);

        const container = document.getElementById('audit-log');
        if (!container) return;

        if (response.entries.length === 0) {
            container.innerHTML = '<p class="text-muted">No audit entries found</p>';
            return;
        }

        container.innerHTML = `
            <table class="audit-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Event</th>
                        <th>Action</th>
                        <th>Status</th>
                        <th>User</th>
                    </tr>
                </thead>
                <tbody>
                    ${response.entries.map(entry => `
                        <tr>
                            <td>${formatTimestamp(entry.timestamp)}</td>
                            <td>${entry.event_type}</td>
                            <td>${entry.action}</td>
                            <td>
                                <span class="status-badge ${entry.success ? 'status-success' : 'status-error'}">
                                    ${entry.success ? '✅' : '❌'}
                                </span>
                            </td>
                            <td>${entry.user_id || 'system'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

    } catch (error) {
        console.error('Failed to load audit log:', error);
    }
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString();
}

// ============================================================================
// EXPORT / RESET
// ============================================================================

async function exportSettings() {
    try {
        const response = await api.get('/api/settings');

        const dataStr = JSON.stringify(response.settings, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });

        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `settings-export-${Date.now()}.json`;
        link.click();

        URL.revokeObjectURL(url);

        toast.success('Settings exported successfully');

    } catch (error) {
        console.error('Failed to export settings:', error);
        toast.error('Failed to export settings');
    }
}

async function resetAllSettings() {
    if (!confirm('Are you sure you want to reset ALL settings to defaults? This cannot be undone.')) {
        return;
    }

    if (!confirm('This will delete all settings from the database. Are you REALLY sure?')) {
        return;
    }

    try {
        // Get all setting keys
        const response = await api.get('/api/settings');

        for (const setting of response.settings) {
            await api.delete(`/api/settings/${setting.key}`);
        }

        toast.success('All settings reset to defaults');

        // Reload page
        window.location.reload();

    } catch (error) {
        console.error('Failed to reset settings:', error);
        toast.error('Failed to reset settings');
    }
}

// ============================================================================
// CONNECTION STATUS & OAUTH AUTHENTICATION
// ============================================================================

async function fetchConnectionStatus(serviceName) {
    try {
        const response = await api.get('/api/monitoring/connections');
        const serviceStatus = response.connections.find(c => c.service_name === serviceName);
        return serviceStatus || {status: 'not_configured', message: 'Not configured'};
    } catch (error) {
        console.error('Failed to fetch connection status:', error);
        return {status: 'error', message: 'Failed to check status'};
    }
}

function getStatusClass(status) {
    const map = {
        'connected': 'status-success',
        'expired': 'status-warning',
        'error': 'status-error',
        'not_configured': 'status-info'
    };
    return map[status] || 'status-info';
}

function getStatusText(status) {
    const map = {
        'connected': '✓ Connected',
        'expired': '⚠ Expired',
        'error': '✗ Error',
        'not_configured': '○ Not Configured'
    };
    return map[status] || '○ Unknown';
}

async function refreshConnectionStatus(service) {
    // Status badges removed - test button is sufficient
    // Keeping this function to avoid breaking existing calls
    return;
}

// ============================================================================
// GOOGLE OAUTH POPUP FLOW
// ============================================================================

async function authenticateGoogle() {
    try {
        toast.info('Starting Google authentication...');

        // Step 1: Get auth URL from backend
        const response = await api.post('/auth/google/initiate');
        const authUrl = response.auth_url + '&popup=true'; // Add popup param

        // Step 2: Open popup window
        const popup = window.open(
            authUrl,
            'googleAuth',
            'width=600,height=700,left=200,top=100'
        );

        if (!popup) {
            toast.error('Popup blocked. Please allow popups for this site.');
            return;
        }

        // Step 3: Listen for success message from popup
        const messageHandler = async (event) => {
            if (event.data.type === 'oauth_success' && event.data.service === 'google') {
                toast.success('Google authentication successful!');
                await refreshConnectionStatus('google');
                window.removeEventListener('message', messageHandler);
            }
        };

        window.addEventListener('message', messageHandler);

        // Clean up listener after 5 minutes
        setTimeout(() => {
            window.removeEventListener('message', messageHandler);
        }, 300000);

    } catch (error) {
        console.error('Google auth failed:', error);
        toast.error('Failed to start authentication: ' + (error.message || 'Unknown error'));
    }
}

// ============================================================================
// OUTLOOK OAUTH DEVICE CODE FLOW
// ============================================================================

let outlookPollingInterval = null;

async function authenticateOutlook() {
    try {
        toast.info('Starting Outlook authentication...');

        // Step 1: Get device code from backend
        const response = await api.post('/auth/outlook/initiate');

        // Step 2: Show modal with device code
        showDeviceCodeModal(response);

        // Step 3: Start polling for completion
        pollOutlookStatus(response.device_code, response.expires_in);

    } catch (error) {
        console.error('Outlook auth failed:', error);
        toast.error('Failed to start authentication: ' + (error.message || 'Unknown error'));
    }
}

function showDeviceCodeModal(data) {
    const modal = document.getElementById('deviceCodeModal');
    const deviceCodeEl = document.getElementById('deviceCode');
    const verificationUrlEl = document.getElementById('verificationUrl');
    const openUrlBtn = document.getElementById('openUrlBtn');

    deviceCodeEl.textContent = data.user_code;
    verificationUrlEl.textContent = data.verification_uri;

    openUrlBtn.onclick = () => {
        window.open(data.verification_uri, '_blank');
    };

    modal.classList.add('active');
}

function closeDeviceCodeModal() {
    const modal = document.getElementById('deviceCodeModal');
    modal.classList.remove('active');

    // Stop polling
    if (outlookPollingInterval) {
        clearInterval(outlookPollingInterval);
        outlookPollingInterval = null;
    }
}

function copyDeviceCode() {
    const deviceCodeEl = document.getElementById('deviceCode');
    const code = deviceCodeEl.textContent;

    navigator.clipboard.writeText(code).then(() => {
        toast.success('Device code copied to clipboard!');
    }).catch(() => {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = code;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        toast.success('Device code copied to clipboard!');
    });
}

async function pollOutlookStatus(deviceCode, expiresIn) {
    const startTime = Date.now();
    const maxTime = expiresIn * 1000;
    const pollInterval = 5000; // Poll every 5 seconds

    const poll = async () => {
        // Check if expired
        if (Date.now() - startTime > maxTime) {
            toast.error('Authentication expired. Please try again.');
            closeDeviceCodeModal();
            return;
        }

        try {
            const response = await api.get(`/auth/outlook/status?device_code=${encodeURIComponent(deviceCode)}`);

            if (response.status === 'success') {
                toast.success('Outlook authentication successful!');
                closeDeviceCodeModal();
                await refreshConnectionStatus('outlook');
            } else if (response.status === 'pending') {
                // Continue polling - interval will handle next call
            } else if (response.status === 'expired') {
                toast.error('Authentication expired. Please try again.');
                closeDeviceCodeModal();
            } else {
                toast.error('Authentication failed: ' + response.message);
                closeDeviceCodeModal();
            }
        } catch (error) {
            console.error('Polling failed:', error);
            // Don't stop polling on network errors, just log them
        }
    };

    // Initial poll
    await poll();

    // Set up interval for continued polling
    outlookPollingInterval = setInterval(poll, pollInterval);
}

// ============================================================================
// GOOGLE ADS OAUTH POPUP FLOW
// ============================================================================

async function authenticateGoogleAds() {
    try {
        toast.info('Starting Google Ads authentication...');

        // Step 1: Get auth URL from backend
        const response = await api.post('/auth/google_ads/initiate');
        const authUrl = response.auth_url + '&popup=true';

        // Step 2: Open popup window
        const popup = window.open(
            authUrl,
            'googleAdsAuth',
            'width=600,height=700,left=200,top=100'
        );

        if (!popup) {
            toast.error('Popup blocked. Please allow popups for this site.');
            return;
        }

        // Step 3: Listen for success message from popup
        const messageHandler = async (event) => {
            if (event.data.type === 'oauth_success' && event.data.service === 'google_ads') {
                toast.success('Google Ads authentication successful!');
                await refreshConnectionStatus('google_ads');
                window.removeEventListener('message', messageHandler);
            }
        };

        window.addEventListener('message', messageHandler);

        // Clean up listener after 5 minutes
        setTimeout(() => {
            window.removeEventListener('message', messageHandler);
        }, 300000);

    } catch (error) {
        console.error('Google Ads auth failed:', error);
        toast.error('Failed to start authentication: ' + (error.message || 'Unknown error'));
    }
}

// ============================================================================
// WHATSAPP QR CODE LINKING
// ============================================================================

let whatsappQrPollingInterval = null;

async function linkWhatsApp() {
    try {
        toast.info('Fetching WhatsApp status...');
        const modal = document.getElementById('whatsappQrModal');
        modal.classList.add('active');

        // Start polling for QR code and connection status
        await pollWhatsAppQr();
        whatsappQrPollingInterval = setInterval(pollWhatsAppQr, 3000);

    } catch (error) {
        console.error('Failed to start WhatsApp linking:', error);
        toast.error('Failed to start WhatsApp linking: ' + (error.message || 'Unknown error'));
    }
}

async function pollWhatsAppQr() {
    try {
        const response = await api.get('/api/whatsapp/status');
        const qrContainer = document.getElementById('whatsappQrCode');
        const statusText = document.getElementById('whatsappQrStatus');

        if (response.ready) {
            // Already connected
            qrContainer.innerHTML = '<p style="color: var(--success-color); font-size: 1.2rem;">Connected</p>';
            statusText.textContent = 'WhatsApp is linked and ready.';
            toast.success('WhatsApp is connected!');
            stopWhatsAppQrPolling();
            setTimeout(closeWhatsAppQrModal, 2000);
            return;
        }

        if (response.has_qr && response.qr_code) {
            // Render QR code
            qrContainer.innerHTML = '<canvas id="whatsappQrCanvas"></canvas>';
            const canvas = document.getElementById('whatsappQrCanvas');
            QRCode.toCanvas(canvas, response.qr_code, {
                width: 280,
                margin: 2,
                color: { dark: '#000000', light: '#ffffff' }
            });
            statusText.textContent = 'Scan this code with your phone to link WhatsApp.';
        } else {
            qrContainer.innerHTML = '<p style="color: var(--text-muted);">Waiting for QR code from bridge...</p>';
            statusText.textContent = 'Make sure the WhatsApp bridge is running.';
        }

    } catch (error) {
        console.error('WhatsApp QR polling error:', error);
        const statusText = document.getElementById('whatsappQrStatus');
        statusText.textContent = 'Could not reach WhatsApp service. Is the bridge running?';
    }
}

function stopWhatsAppQrPolling() {
    if (whatsappQrPollingInterval) {
        clearInterval(whatsappQrPollingInterval);
        whatsappQrPollingInterval = null;
    }
}

function closeWhatsAppQrModal() {
    const modal = document.getElementById('whatsappQrModal');
    modal.classList.remove('active');
    stopWhatsAppQrPolling();

    // Reset modal content
    document.getElementById('whatsappQrCode').innerHTML =
        '<p style="color: var(--text-muted);">Waiting for QR code...</p>';
    document.getElementById('whatsappQrStatus').textContent =
        'Waiting for authentication...';
}

// ============================================================================
// TEST CONNECTION
// ============================================================================

async function testConnection(service) {
    try {
        // Show loading state
        toast.info(`Testing ${service} connection...`);

        // Try service-specific test endpoint first
        let response;
        try {
            // Service-specific endpoints
            const serviceEndpoints = {
                'google': '/api/google/test-connection',
                'google_navigator': '/api/google_navigator/test-connection',
                'google_ads': '/api/google_ads/test-connection',
                'outlook': '/api/outlook/test-connection',
                'notion': '/api/notion/test-connection',
                'nextcloud': '/api/nextcloud/test-connection',
                'whatsapp': '/api/whatsapp/test-connection',
                'slack': '/api/slack/test-connection',
                'brave': '/api/brave/test-connection',
                'browser': '/api/browser/test-connection',
                'whisper': '/api/whisper/test-connection',
                'mistral_ocr': '/api/mistral-ocr/test-connection',
                'toggl': '/api/toggl/test-connection',
                'google_news': '/api/google-news/test-connection',
                'yahoo_finance': '/api/yahoo-finance/test-connection'
            };

            if (serviceEndpoints[service]) {
                response = await api.post(serviceEndpoints[service]);
            } else {
                // Fall back to generic test endpoint
                response = await api.post(`/api/settings/credentials/${service}/test`);
            }
        } catch (serviceError) {
            // If service-specific endpoint fails, try generic
            response = await api.post(`/api/settings/credentials/${service}/test`);
        }

        // Show result
        if (response.status === 'connected' || response.status === 'success') {
            toast.success(`✓ ${service} connection successful!`);
        } else if (response.status === 'warning') {
            // For warning status, show as info with better message
            toast.info(`${service}: Credentials configured. ${response.message}`);
        } else if (response.status === 'oauth_required') {
            // OAuth needs to be completed first
            toast.warning(`${service}: ${response.message}`);
            if (response.auth_url) {
                console.log('OAuth URL:', response.auth_url);
                // Could open auth URL in popup if needed
            }
        } else if (response.status === 'error') {
            toast.error(`✗ ${response.message}`);
        } else {
            toast.warning(`${service}: ${response.message || 'Unknown status'}`);
        }

        // Refresh status badge
        await refreshConnectionStatus(service);

    } catch (error) {
        console.error('Connection test failed:', error);
        toast.error(`Connection test failed: ${error.detail || error.message || 'Unknown error'}`);
    }
}

// ============================================================================
// AGENTS MANAGEMENT
// ============================================================================

async function loadAgents() {
    try {
        const agentsResponse = await api.get('/api/agents');
        settingsState.agents = agentsResponse.agents;
        renderAgentsList();
    } catch (error) {
        console.error('Failed to load agents:', error);
        throw error;
    }
}

function renderAgentsList() {
    const container = document.getElementById('agents-list');
    if (!container) return;

    if (settingsState.agents.length === 0) {
        container.innerHTML = '<p class="text-muted">No agents configured</p>';
        return;
    }

    container.innerHTML = settingsState.agents.map((agent, index) =>
        createAgentCard(agent, index, settingsState.agents.length)
    ).join('');
}

function createAgentCard(agent, index, total) {
    const toolsCount = agent.tools ? agent.tools.length : 0;
    const statusClass = agent.enabled ? 'status-success' : 'status-warning';
    const statusText = agent.enabled ? 'Enabled' : 'Disabled';
    const isCoordinator = agent.name === 'coordinator';

    const upDisabled = index === 0 ? 'disabled' : '';
    const downDisabled = index === total - 1 ? 'disabled' : '';

    return `
        <div class="agent-card" id="agent-${agent.name}">
            <div class="agent-header">
                <div class="agent-title">
                    <div class="agent-priority-controls">
                        <button class="btn-priority" onclick="moveAgent('${agent.name}', 'up')" ${upDisabled} title="Move up">&#9650;</button>
                        <button class="btn-priority" onclick="moveAgent('${agent.name}', 'down')" ${downDisabled} title="Move down">&#9660;</button>
                    </div>
                    <span class="agent-icon">${getAgentIcon(agent.name)}</span>
                    <div class="agent-info">
                        <h4>${agent.display_name}</h4>
                        <small class="text-muted">${agent.role}</small>
                    </div>
                </div>
                <div class="agent-actions">
                    <span class="status-badge ${statusClass}">${statusText}</span>
                    <label class="toggle-label" ${isCoordinator ? 'title="Coordinator cannot be disabled"' : ''}>
                        <input
                            type="checkbox"
                            class="toggle-input"
                            ${agent.enabled ? 'checked' : ''}
                            ${isCoordinator ? 'disabled' : ''}
                            onchange="toggleAgent('${agent.name}', this.checked)"
                        >
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
            <div class="agent-body">
                <p class="agent-goal">${agent.goal}</p>
                <div class="agent-meta">
                    <span class="meta-item">${toolsCount} tools assigned</span>
                    ${agent.allow_delegation ? '<span class="meta-item">Can delegate</span>' : ''}
                    <span class="meta-item">Priority: ${agent.priority || index + 1}</span>
                </div>
            </div>
            <div class="agent-footer">
                <button onclick="openAgentModal('${agent.name}')" class="btn btn-secondary btn-sm">
                    Edit Prompt
                </button>
                ${!isCoordinator ? `<button onclick="deleteAgent('${agent.name}')" class="btn btn-danger btn-sm">Remove</button>` : ''}
            </div>
        </div>
    `;
}

function getAgentIcon(agentName) {
    const icons = {
        coordinator: '🎯',
        research: '🔍',
        communication: '📨',
        planner: '📅',
        browser: '🌐',
        writer: '✍️',
        file_handler: '📁',
        system: '⚙️',
        navigator: '🗺️'
    };
    return icons[agentName] || '🤖';
}

async function moveAgent(agentName, direction) {
    const index = settingsState.agents.findIndex(a => a.name === agentName);
    if (index === -1) return;

    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= settingsState.agents.length) return;

    // Swap in local state
    const temp = settingsState.agents[index];
    settingsState.agents[index] = settingsState.agents[newIndex];
    settingsState.agents[newIndex] = temp;

    // Re-render immediately for responsiveness
    renderAgentsList();

    // Save new order to backend
    try {
        const agentOrder = settingsState.agents.map(a => a.name);
        await api.post('/api/agents/reorder', { agent_order: agentOrder });
    } catch (error) {
        console.error('Failed to save agent order:', error);
        toast.error('Failed to save agent order');
    }
}

async function toggleAgent(agentName, enabled) {
    try {
        await api.post(`/api/agents/${agentName}/toggle`, { enabled });

        const agent = settingsState.agents.find(a => a.name === agentName);
        if (agent) {
            agent.enabled = enabled;
        }

        renderAgentsList();
        toast.success(`${agentName} agent ${enabled ? 'enabled' : 'disabled'}`);

    } catch (error) {
        console.error('Failed to toggle agent:', error);
        toast.error('Failed to update agent status');
        const checkbox = document.querySelector(`#agent-${agentName} .toggle-input`);
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

async function deleteAgent(agentName) {
    if (!confirm(`Are you sure you want to remove the "${agentName}" agent? This cannot be undone.`)) {
        return;
    }

    try {
        await api.delete(`/api/agents/${agentName}`);
        settingsState.agents = settingsState.agents.filter(a => a.name !== agentName);
        renderAgentsList();
        toast.success(`Agent "${agentName}" removed`);
    } catch (error) {
        console.error('Failed to delete agent:', error);
        toast.error('Failed to remove agent: ' + (error.message || 'Unknown error'));
    }
}

async function openAgentModal(agentName) {
    try {
        const agent = settingsState.agents.find(a => a.name === agentName);
        if (!agent) {
            toast.error('Agent not found');
            return;
        }

        settingsState.currentAgent = agentName;

        document.getElementById('agent-name').value = agent.name;
        document.getElementById('agent-display-name').value = agent.display_name;
        document.getElementById('agent-role').value = agent.role;
        document.getElementById('agent-goal').value = agent.goal;
        document.getElementById('agent-backstory').value = agent.backstory;
        document.getElementById('agent-priority').value = agent.priority || 5;
        document.getElementById('agent-intent-keywords').value = (agent.intent_keywords || []).join(', ');
        document.getElementById('agent-modal-title').textContent = `Edit ${agent.display_name}`;

        // Show/hide reset button based on whether this is a default agent
        const resetBtn = document.getElementById('agent-reset-btn');
        if (resetBtn) {
            const defaultAgents = ['coordinator', 'research', 'communication', 'writer', 'file_handler', 'planner', 'system', 'navigator', 'browser'];
            resetBtn.style.display = defaultAgents.includes(agentName) ? 'inline-block' : 'none';
        }

        document.getElementById('agentModal').style.display = 'flex';

    } catch (error) {
        console.error('Failed to open agent modal:', error);
        toast.error('Failed to load agent details');
    }
}

function closeAgentModal() {
    document.getElementById('agentModal').style.display = 'none';
    settingsState.currentAgent = null;
}

async function saveAgentSettings() {
    try {
        const agentName = settingsState.currentAgent;
        if (!agentName) {
            toast.error('No agent selected');
            return;
        }

        // Collect form values, omitting empty strings (backend requires min_length=1)
        const updates = {};
        const fields = ['display_name', 'role', 'goal', 'backstory'];
        for (const f of fields) {
            const val = document.getElementById(`agent-${f.replace('_', '-')}`).value;
            if (val) updates[f] = val;
        }
        const priority = parseInt(document.getElementById('agent-priority').value);
        if (priority) updates.priority = priority;

        const keywordsRaw = document.getElementById('agent-intent-keywords').value;
        const intentKeywords = keywordsRaw
            ? keywordsRaw.split(',').map(k => k.trim()).filter(k => k.length > 0)
            : [];
        if (intentKeywords.length > 0) updates.intent_keywords = intentKeywords;

        const response = await api.put(`/api/agents/${agentName}`, updates);

        const index = settingsState.agents.findIndex(a => a.name === agentName);
        if (index !== -1) {
            settingsState.agents[index] = response;
        }

        renderAgentsList();
        toast.success('Agent settings saved');
        closeAgentModal();

    } catch (error) {
        console.error('Failed to save agent settings:', error);
        toast.error('Failed to save agent settings: ' + (error.message || 'Unknown error'));
    }
}

async function resetAgentToDefault() {
    try {
        const agentName = settingsState.currentAgent;
        if (!agentName) {
            toast.error('No agent selected');
            return;
        }

        if (!confirm(`Reset ${agentName} agent to default configuration?`)) {
            return;
        }

        const response = await api.post(`/api/agents/${agentName}/reset`);

        const index = settingsState.agents.findIndex(a => a.name === agentName);
        if (index !== -1) {
            settingsState.agents[index] = response;
        }

        renderAgentsList();
        toast.success('Agent reset to default');
        closeAgentModal();

    } catch (error) {
        console.error('Failed to reset agent:', error);
        toast.error('Failed to reset agent: ' + (error.message || 'Unknown error'));
    }
}

// ============================================================================
// ADD AGENT
// ============================================================================

function openAddAgentModal() {
    document.getElementById('new-agent-name').value = '';
    document.getElementById('new-agent-display-name').value = '';
    document.getElementById('new-agent-role').value = '';
    document.getElementById('new-agent-goal').value = '';
    document.getElementById('new-agent-backstory').value = '';
    document.getElementById('addAgentModal').style.display = 'flex';
}

function closeAddAgentModal() {
    document.getElementById('addAgentModal').style.display = 'none';
}

async function createNewAgent() {
    try {
        const name = document.getElementById('new-agent-name').value.trim();
        const displayName = document.getElementById('new-agent-display-name').value.trim();
        const role = document.getElementById('new-agent-role').value.trim();
        const goal = document.getElementById('new-agent-goal').value.trim();
        const backstory = document.getElementById('new-agent-backstory').value.trim();

        if (!name || !displayName || !role || !goal) {
            toast.error('Name, display name, role, and goal are required');
            return;
        }

        if (!/^[a-z_]+$/.test(name)) {
            toast.error('Agent ID must contain only lowercase letters and underscores');
            return;
        }

        // Calculate next priority
        const maxPriority = settingsState.agents.length > 0
            ? Math.max(...settingsState.agents.map(a => a.priority || 0))
            : 0;

        const response = await api.post('/api/agents', {
            name,
            display_name: displayName,
            role,
            goal,
            backstory: backstory || '',
            priority: maxPriority + 1,
            enabled: true
        });

        settingsState.agents.push(response);
        renderAgentsList();
        closeAddAgentModal();
        toast.success(`Agent "${displayName}" created`);

    } catch (error) {
        console.error('Failed to create agent:', error);
        toast.error('Failed to create agent: ' + (error.detail || error.message || 'Unknown error'));
    }
}

// ============================================================================
// TOOLS TAB - DRAG & DROP
// ============================================================================

const SERVICE_ICONS = {
    google: '🔵',
    google_navigator: '🗺️',
    outlook: '📨',
    notion: '📝',
    nextcloud: '☁️',
    whatsapp: '💬',
    slack: '📢',
    brave: '🔎',
    browser: '🌐',
    google_news: '📰',
    system: '⚙️'
};

function escapeHtmlText(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function loadToolsGrouped() {
    try {
        const response = await api.get('/api/agents/tools-grouped');
        settingsState.toolsGrouped = response.groups;
        settingsState.toolsAgentList = response.agents;
        settingsState.pendingToolAssignments = {};

        // Build initial assignments from current data
        for (const [service, tools] of Object.entries(response.groups)) {
            for (const tool of tools) {
                settingsState.pendingToolAssignments[tool.tool_name] = tool.agent_name || null;
            }
        }

        renderToolsDragDrop();
    } catch (error) {
        console.error('Failed to load tools:', error);
        throw error;
    }
}

function getAllToolsFlat() {
    const tools = [];
    for (const [service, serviceTools] of Object.entries(settingsState.toolsGrouped)) {
        for (const tool of serviceTools) {
            tools.push({ ...tool, service });
        }
    }
    return tools;
}

function buildToolChip(tool) {
    const icon = SERVICE_ICONS[tool.service] || '🔧';
    const name = escapeAttr(tool.tool_name);
    const displayName = escapeHtmlText(tool.display_name);
    const description = escapeAttr(tool.description || '');
    return `<div class="tool-chip" draggable="true" data-tool="${name}" title="${description}" ondragstart="onToolDragStart(event)">${icon} ${displayName}</div>`;
}

function buildDropZone(label, zoneId, tools) {
    const chips = tools.map(t => buildToolChip(t)).join('');
    const escapedLabel = escapeHtmlText(label);
    const count = tools.length;
    return `
        <div class="tool-drop-zone" data-zone="${escapeAttr(zoneId)}"
             ondragover="onToolDragOver(event)" ondragleave="onToolDragLeave(event)" ondrop="onToolDrop(event)">
            <div class="tool-zone-header">${escapedLabel} <span class="tool-zone-count">(${count})</span></div>
            <div class="tool-zone-body">${chips || '<span class="tool-zone-empty">Drop tools here</span>'}</div>
        </div>
    `;
}

function renderToolsDragDrop() {
    const container = document.getElementById('tools-dnd-container');
    if (!container) return;

    const allTools = getAllToolsFlat();
    if (allTools.length === 0) {
        container.innerHTML = '<p class="text-muted">No tools available</p>';
        return;
    }

    // Group tools by assigned agent
    const unassigned = allTools.filter(t => !settingsState.pendingToolAssignments[t.tool_name]);
    const agentZones = settingsState.toolsAgentList.map(agent => {
        const agentTools = allTools.filter(t => settingsState.pendingToolAssignments[t.tool_name] === agent.name);
        return { agent, tools: agentTools };
    });

    let html = buildDropZone('Unassigned', '__unassigned__', unassigned);
    for (const { agent, tools } of agentZones) {
        const icon = getAgentIcon(agent.name);
        html += buildDropZone(`${icon} ${agent.display_name}`, agent.name, tools);
    }

    container.innerHTML = html;
}

function onToolDragStart(event) {
    event.dataTransfer.setData('text/plain', event.target.dataset.tool);
    event.dataTransfer.effectAllowed = 'move';
    event.target.classList.add('tool-chip-dragging');
}

function onToolDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const zone = event.currentTarget;
    zone.classList.add('tool-drop-zone-over');
}

function onToolDragLeave(event) {
    const zone = event.currentTarget;
    // Only remove highlight if we actually left the zone
    if (!zone.contains(event.relatedTarget)) {
        zone.classList.remove('tool-drop-zone-over');
    }
}

async function onToolDrop(event) {
    event.preventDefault();
    const zone = event.currentTarget;
    zone.classList.remove('tool-drop-zone-over');

    const toolName = event.dataTransfer.getData('text/plain');
    if (!toolName) return;

    const targetAgent = zone.dataset.zone;
    const agentName = targetAgent === '__unassigned__' ? null : targetAgent;
    const previousAgent = settingsState.pendingToolAssignments[toolName] || null;

    // No-op if dropped on the same zone
    if (agentName === previousAgent) return;

    // Optimistic UI update
    settingsState.pendingToolAssignments[toolName] = agentName;
    renderToolsDragDrop();

    // Persist via single-tool endpoint
    try {
        await api.put('/api/agents/tool-assignment', {
            tool_name: toolName,
            agent_name: agentName
        });
        // Invalidate agents cache since tools changed
        settingsState.agentsLoaded = false;
    } catch (error) {
        console.error('Failed to save tool assignment:', error);
        toast.error('Failed to save tool assignment');
        // Revert on failure
        settingsState.pendingToolAssignments[toolName] = previousAgent;
        renderToolsDragDrop();
    }
}

// ============================================================================
// PLUGINS
// ============================================================================

async function loadPlugins() {
    try {
        const plugins = await api.get('/api/plugins');
        const container = document.getElementById('plugins-list');
        container.innerHTML = '';

        if (!plugins || plugins.length === 0) {
            container.innerHTML = '<p class="text-muted">No plugins available.</p>';
            return;
        }

        for (const plugin of plugins) {
            const card = createPluginCard(plugin);
            container.appendChild(card);
        }
    } catch (error) {
        console.error('Failed to load plugins:', error);
        toast.error('Failed to load plugins');
    }
}

function createPluginCard(plugin) {
    const card = document.createElement('div');
    card.className = 'integration-card';
    card.id = `plugin-card-${plugin.id}`;

    const authLabel = {
        bearer: 'Bearer Token',
        header: 'API Key Header',
        basic: 'Basic Auth',
        api_key_with_jwt: 'API Key + JWT'
    }[plugin.auth_type] || plugin.auth_type;

    // Build credential fields based on auth type
    let credentialFields = '';
    if (plugin.auth_type === 'bearer' || plugin.auth_type === 'header') {
        credentialFields = `
            <div class="form-group">
                <label class="form-label">API Token / Secret</label>
                <div class="input-group">
                    <input type="password" id="plugin-token-${plugin.id}" class="form-input masked-input"
                        placeholder="Enter token..." value="${plugin.has_credentials ? '***MASKED***' : ''}">
                    <button type="button" onclick="toggleMasked('plugin-token-${plugin.id}')" class="btn-icon">👁️</button>
                </div>
            </div>`;
    } else if (plugin.auth_type === 'basic') {
        if (plugin.has_fixed_password) {
            // Fixed-password basic auth (e.g. Toggl): only need the token/username
            credentialFields = `
                <div class="form-group">
                    <label class="form-label">API Token</label>
                    <div class="input-group">
                        <input type="password" id="plugin-token-${plugin.id}" class="form-input masked-input"
                            placeholder="Enter API token..." value="${plugin.has_credentials ? '***MASKED***' : ''}">
                        <button type="button" onclick="toggleMasked('plugin-token-${plugin.id}')" class="btn-icon">👁️</button>
                    </div>
                </div>`;
        } else {
            // Full username + password basic auth (e.g. WordPress)
            credentialFields = `
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <div class="input-group">
                        <input type="password" id="plugin-token-${plugin.id}" class="form-input masked-input"
                            placeholder="Enter username..." value="${plugin.has_credentials ? '***MASKED***' : ''}">
                        <button type="button" onclick="toggleMasked('plugin-token-${plugin.id}')" class="btn-icon">👁️</button>
                    </div>
                </div>
                <div class="form-group" id="plugin-password-group-${plugin.id}">
                    <label class="form-label">Password <span class="text-muted">(leave blank to keep existing)</span></label>
                    <div class="input-group">
                        <input type="password" id="plugin-password-${plugin.id}" class="form-input masked-input" placeholder="Enter password...">
                        <button type="button" onclick="toggleMasked('plugin-password-${plugin.id}')" class="btn-icon">👁️</button>
                    </div>
                </div>`;
        }
    } else if (plugin.auth_type === 'api_key_with_jwt') {
        // Static API key header + JWT obtained via username/password login
        credentialFields = `
            <div class="form-group">
                <label class="form-label">API Key <span class="text-muted">(sent as static header on every request)</span></label>
                <div class="input-group">
                    <input type="password" id="plugin-apikey-${plugin.id}" class="form-input masked-input"
                        placeholder="Enter API key..." value="${plugin.has_credentials ? '***MASKED***' : ''}">
                    <button type="button" onclick="toggleMasked('plugin-apikey-${plugin.id}')" class="btn-icon">👁️</button>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Username</label>
                <div class="input-group">
                    <input type="text" id="plugin-token-${plugin.id}" class="form-input"
                        placeholder="Enter username..." value="${plugin.has_credentials ? '***MASKED***' : ''}">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Password <span class="text-muted">(leave blank to keep existing)</span></label>
                <div class="input-group">
                    <input type="password" id="plugin-password-${plugin.id}" class="form-input masked-input" placeholder="Enter password...">
                    <button type="button" onclick="toggleMasked('plugin-password-${plugin.id}')" class="btn-icon">👁️</button>
                </div>
            </div>`;
    }

    // Build non-sensitive config fields
    let configFieldsHtml = '';
    for (const field of (plugin.config_fields || [])) {
        if (!field.sensitive) {
            configFieldsHtml += `
                <div class="form-group">
                    <label class="form-label">${field.display_name}${field.required ? ' <span style="color:#ff4444">*</span>' : ''}</label>
                    <input type="text" id="plugin-config-${plugin.id}-${field.key}" class="form-input"
                        placeholder="${field.placeholder || ''}"
                        data-config-key="${field.key}">
                    ${field.description ? `<div class="form-hint">${field.description}</div>` : ''}
                </div>`;
        }
    }

    const isBuiltin = plugin.is_builtin;

    card.innerHTML = `
        <div class="integration-header" onclick="togglePluginCard('${plugin.id}')">
            <div class="integration-title">
                <span class="integration-icon">${plugin.icon}</span>
                <h4>${plugin.display_name}<span class="text-muted" style="font-size:0.82rem; margin-left:8px; font-weight:400;">${authLabel} · ${plugin.endpoint_count} tool${plugin.endpoint_count !== 1 ? 's' : ''}</span>${isBuiltin ? '' : '<span class="status-badge status-info" style="font-size:0.72rem; margin-left:6px;">custom</span>'}</h4>
                <span class="expand-icon" id="plugin-chevron-${plugin.id}">▼</span>
            </div>
            <label class="toggle-label" onclick="event.stopPropagation()">
                <input type="checkbox" class="toggle-input" id="plugin-enabled-${plugin.id}"
                    ${plugin.enabled ? 'checked' : ''}
                    onchange="togglePlugin('${plugin.id}', this.checked)">
                <span class="toggle-slider"></span>
            </label>
        </div>
        <div class="integration-body" id="plugin-body-${plugin.id}" style="display:none;">
            <p class="text-muted" style="margin-bottom:16px;">${plugin.description}</p>

            ${credentialFields}
            ${configFieldsHtml}

            <div class="integration-actions">
                <button onclick="savePluginCredentials('${plugin.id}')" class="btn btn-primary">💾 Save</button>
                <button onclick="testPluginConnection('${plugin.id}')" class="btn btn-secondary">🔍 Test Connection</button>
                ${!isBuiltin ? `<button onclick="showEditPluginModal('${plugin.id}')" class="btn btn-secondary">✏️ Edit JSON</button>` : ''}
                ${!isBuiltin ? `<button onclick="deletePlugin('${plugin.id}')" class="btn btn-danger">🗑 Delete</button>` : ''}
            </div>
            <div id="plugin-status-${plugin.id}" style="margin-top:8px;"></div>
        </div>`;

    // Load current config values async
    loadPluginConfigValues(plugin.id, plugin.config_fields || []);

    return card;
}

async function loadPluginConfigValues(pluginId, configFields) {
    if (!configFields.some(f => !f.sensitive)) return;
    try {
        const data = await api.get(`/api/plugins/${pluginId}/config`);
        for (const field of configFields) {
            if (!field.sensitive) {
                const input = document.getElementById(`plugin-config-${pluginId}-${field.key}`);
                if (input && data.config_values && data.config_values[field.key]) {
                    input.value = data.config_values[field.key];
                }
            }
        }
    } catch (e) {
        // Non-critical — silently ignore
    }
}

function togglePluginCard(pluginId) {
    const body = document.getElementById(`plugin-body-${pluginId}`);
    const chevron = document.getElementById(`plugin-chevron-${pluginId}`);
    if (body.style.display === 'none') {
        body.style.display = 'block';
        chevron.textContent = '▲';
    } else {
        body.style.display = 'none';
        chevron.textContent = '▼';
    }
}

async function togglePlugin(pluginId, enabled) {
    try {
        await api.put(`/api/plugins/${pluginId}/enable`, { enabled });
        toast.success(`Plugin ${enabled ? 'enabled' : 'disabled'}`);
    } catch (error) {
        console.error('Failed to toggle plugin:', error);
        toast.error('Failed to update plugin');
        // Revert checkbox
        const cb = document.getElementById(`plugin-enabled-${pluginId}`);
        if (cb) cb.checked = !enabled;
    }
}

async function savePluginCredentials(pluginId) {
    const statusEl = document.getElementById(`plugin-status-${pluginId}`);

    const tokenInput = document.getElementById(`plugin-token-${pluginId}`);
    const passwordInput = document.getElementById(`plugin-password-${pluginId}`);
    const apiKeyInput = document.getElementById(`plugin-apikey-${pluginId}`);

    const body = { config: {} };

    if (apiKeyInput && apiKeyInput.value && apiKeyInput.value !== '***MASKED***') {
        body.api_key = apiKeyInput.value;
    }
    if (tokenInput && tokenInput.value && tokenInput.value !== '***MASKED***') {
        body.token = tokenInput.value;
        // For basic auth without fixed_password, token field is the username
        body.username = tokenInput.value;
    }
    if (passwordInput && passwordInput.value) {
        body.password = passwordInput.value;
    }

    // Collect non-sensitive config fields
    const card = document.getElementById(`plugin-card-${pluginId}`);
    if (card) {
        card.querySelectorAll('[data-config-key]').forEach(input => {
            if (input.value) {
                body.config[input.dataset.configKey] = input.value;
            }
        });
    }

    try {
        await api.put(`/api/plugins/${pluginId}/credentials`, body);
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#00cc66;">✓ Saved</span>';
            setTimeout(() => { statusEl.innerHTML = ''; }, 3000);
        }
        toast.success('Plugin credentials saved');
    } catch (error) {
        console.error('Failed to save plugin credentials:', error);
        if (statusEl) statusEl.innerHTML = '<span style="color:#ff4444;">✗ Save failed</span>';
        toast.error('Failed to save credentials');
    }
}

async function testPluginConnection(pluginId) {
    const statusEl = document.getElementById(`plugin-status-${pluginId}`);
    if (statusEl) statusEl.innerHTML = '<span class="text-muted">Testing...</span>';

    try {
        const result = await api.get(`/api/plugins/${pluginId}/test`);
        if (result.success) {
            if (statusEl) statusEl.innerHTML = `<span style="color:#00cc66;">✓ ${result.message}</span>`;
            toast.success('Connection successful');
        } else {
            if (statusEl) statusEl.innerHTML = `<span style="color:#ff4444;">✗ ${result.message}</span>`;
            toast.error(`Connection failed: ${result.message}`);
        }
    } catch (error) {
        console.error('Plugin test failed:', error);
        if (statusEl) statusEl.innerHTML = '<span style="color:#ff4444;">✗ Test failed</span>';
        toast.error('Connection test failed');
    }
}

async function deletePlugin(pluginId) {
    if (!confirm(`Delete plugin "${pluginId}"? This cannot be undone.`)) return;
    try {
        await api.delete(`/api/plugins/${pluginId}`);
        const card = document.getElementById(`plugin-card-${pluginId}`);
        if (card) card.remove();
        toast.success('Plugin deleted');
    } catch (error) {
        console.error('Failed to delete plugin:', error);
        toast.error('Failed to delete plugin');
    }
}

// Tracks the plugin id being edited, or null when adding a new plugin.
let _editingPluginId = null;

function showAddPluginModal() {
    _editingPluginId = null;
    document.getElementById('plugin-json-input').value = '';
    document.getElementById('plugin-json-error').style.display = 'none';
    document.getElementById('plugin-modal-title').textContent = 'Install Custom Plugin';
    document.getElementById('plugin-modal-save-btn').textContent = 'Validate & Install';
    document.getElementById('addPluginModal').style.display = 'flex';
}

async function showEditPluginModal(pluginId) {
    _editingPluginId = pluginId;
    document.getElementById('plugin-json-error').style.display = 'none';
    document.getElementById('plugin-modal-title').textContent = 'Edit Plugin JSON';
    document.getElementById('plugin-modal-save-btn').textContent = 'Validate & Save';
    document.getElementById('plugin-json-input').value = 'Loading...';
    document.getElementById('addPluginModal').style.display = 'flex';

    try {
        const defn = await api.get(`/api/plugins/${pluginId}/definition`);
        document.getElementById('plugin-json-input').value = JSON.stringify(defn, null, 2);
    } catch (error) {
        document.getElementById('plugin-json-input').value = '';
        const errorEl = document.getElementById('plugin-json-error');
        errorEl.textContent = `Failed to load plugin definition: ${error.detail || error.message}`;
        errorEl.style.display = 'block';
    }
}

function closeAddPluginModal() {
    document.getElementById('addPluginModal').style.display = 'none';
    _editingPluginId = null;
}

async function savePluginJson() {
    if (_editingPluginId) {
        await _updatePlugin(_editingPluginId);
    } else {
        await _installPlugin();
    }
}

async function _installPlugin() {
    const textarea = document.getElementById('plugin-json-input');
    const errorEl = document.getElementById('plugin-json-error');
    errorEl.style.display = 'none';

    let parsed;
    try {
        parsed = JSON.parse(textarea.value);
    } catch (e) {
        errorEl.textContent = `Invalid JSON: ${e.message}`;
        errorEl.style.display = 'block';
        return;
    }

    if (!parsed.id || !parsed.display_name || !parsed.endpoints || !parsed.auth) {
        errorEl.textContent = 'Missing required fields: id, display_name, auth, endpoints';
        errorEl.style.display = 'block';
        return;
    }

    try {
        const newPlugin = await api.post('/api/plugins', parsed);
        closeAddPluginModal();
        const container = document.getElementById('plugins-list');
        const card = createPluginCard(newPlugin);
        container.appendChild(card);
        settingsState.pluginsLoaded = true;
        toast.success(`Plugin "${newPlugin.display_name}" installed`);
    } catch (error) {
        const msg = error.detail || error.message || 'Validation failed';
        errorEl.textContent = `Install failed: ${msg}`;
        errorEl.style.display = 'block';
    }
}

async function _updatePlugin(pluginId) {
    const textarea = document.getElementById('plugin-json-input');
    const errorEl = document.getElementById('plugin-json-error');
    errorEl.style.display = 'none';

    let parsed;
    try {
        parsed = JSON.parse(textarea.value);
    } catch (e) {
        errorEl.textContent = `Invalid JSON: ${e.message}`;
        errorEl.style.display = 'block';
        return;
    }

    if (!parsed.id || !parsed.display_name || !parsed.endpoints || !parsed.auth) {
        errorEl.textContent = 'Missing required fields: id, display_name, auth, endpoints';
        errorEl.style.display = 'block';
        return;
    }

    try {
        const updated = await api.put(`/api/plugins/${pluginId}/definition`, parsed);
        closeAddPluginModal();
        // Replace the existing card with a refreshed one
        const oldCard = document.getElementById(`plugin-card-${pluginId}`);
        const newCard = createPluginCard(updated);
        if (oldCard) {
            oldCard.replaceWith(newCard);
        } else {
            document.getElementById('plugins-list').appendChild(newCard);
        }
        toast.success(`Plugin "${updated.display_name}" updated`);
    } catch (error) {
        const msg = error.detail || error.message || 'Validation failed';
        errorEl.textContent = `Update failed: ${msg}`;
        errorEl.style.display = 'block';
    }
}

// Keep backward-compat alias used by the HTML onclick in older cached pages.
async function installPlugin() { await savePluginJson(); }
