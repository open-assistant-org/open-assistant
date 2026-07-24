// Chat functionality with conversation persistence

let conversationId = storage.get('current_conversation_id');
let conversationHistory = [];

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const newConversationBtn = document.getElementById('newConversationBtn');
const conversationIdDisplay = document.getElementById('conversationIdDisplay');
const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
const chatLayout = document.getElementById('chatLayout');
const conversationSearch = document.getElementById('conversationSearch');
const dateFilter = document.getElementById('dateFilter');
const loadMoreBtn = document.getElementById('loadMoreConversations');

// Initialize
function init() {
    loadConversationHistory();
    setupEventListeners();
    updateConversationDisplay();
    loadIntegrationStatus();
}

// Load integration status
async function loadIntegrationStatus() {
    try {
        const response = await api.get('/api/integrations/status');
        displayIntegrationStatus(response);
    } catch (error) {
        console.error('Failed to load integration status:', error);
        // Non-critical error, continue without integration status
    }
}

function displayIntegrationStatus(status) {
    // Add a subtle indicator in the UI showing available integrations
    const statusDiv = document.createElement('div');
    statusDiv.className = 'integration-status';
    statusDiv.style.cssText = `
        padding: 8px 12px;
        margin: 8px 0;
        background: rgba(59, 130, 246, 0.1);
        border-radius: 6px;
        font-size: 0.875rem;
        color: #4b5563;
    `;

    const toolCount = status.available_tools.length;
    statusDiv.innerHTML = `
        <div class="integration-badge" style="margin-bottom: 4px;">
            🔌 ${toolCount} integration tool${toolCount !== 1 ? 's' : ''} available
        </div>
    `;

    // Show which integrations are active
    const activeIntegrations = Object.entries(status.integrations)
        .filter(([_, info]) => info.available)
        .map(([name, _]) => name);

    if (activeIntegrations.length > 0) {
        statusDiv.innerHTML += `
            <div class="active-integrations" style="font-size: 0.8rem; color: #6b7280;">
                Active: ${activeIntegrations.join(', ')}
            </div>
        `;
    } else {
        statusDiv.innerHTML += `
            <div class="active-integrations" style="font-size: 0.8rem; color: #9ca3af;">
                No integrations configured. Configure them in Settings.
            </div>
        `;
    }

    // Insert at the top of chat container
    const chatContainer = chatMessages.parentElement;
    if (chatContainer && chatMessages) {
        chatContainer.insertBefore(statusDiv, chatMessages);
    }
}

// Setup event listeners
function setupEventListeners() {
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    if (newConversationBtn) {
        newConversationBtn.addEventListener('click', startNewConversation);
    }

    // Sidebar controls
    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', () => {
            historyManager.toggleSidebar();
        });
    }

    if (sidebarCloseBtn) {
        sidebarCloseBtn.addEventListener('click', () => {
            historyManager.toggleSidebar();
        });
    }

    // Search with debounce
    if (conversationSearch) {
        conversationSearch.addEventListener('input', debounce((e) => {
            historyManager.searchConversations(e.target.value);
        }, 500));
    }

    // Date filter
    if (dateFilter) {
        dateFilter.addEventListener('change', (e) => {
            historyManager.filterByDate(e.target.value);
        });
    }

    // Load more button
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            historyManager.loadConversations(true);
        });
    }
}

// Load conversation history
async function loadConversationHistory() {
    if (!conversationId) return;

    try {
        const response = await api.get(`/api/conversations/${conversationId}/messages?limit=50`);
        conversationHistory = response.messages || [];

        // Display messages
        chatMessages.innerHTML = '';
        conversationHistory.forEach(msg => {
            addMessageToUI(msg.content, msg.role);
        });

    } catch (error) {
        console.error('Failed to load conversation history:', error);
        // Start fresh if conversation not found
        if (error.message.includes('404')) {
            startNewConversation();
        }
    }
}

// Send message — uses SSE streaming when supported, falls back to plain POST
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessageToUI(message, 'user');
    messageInput.value = '';

    messageInput.disabled = true;
    sendButton.disabled = true;
    showTypingIndicator();

    // Streaming path (modern browsers)
    if (typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined') {
        try {
            await sendMessageStreaming(message);
        } catch (error) {
            hideTypingIndicator();
            console.error('Streaming error:', error);
            toast.error(error.message || 'Failed to get response');
            addMessageToUI('Sorry, I encountered an error. Please try again.', 'error');
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            messageInput.focus();
        }
        return;
    }

    // Fallback: plain POST (no streaming)
    try {
        const response = await api.post('/api/chat', {
            message: message,
            conversation_id: conversationId,
            channel: 'webui'
        });
        if (response.conversation_id) {
            conversationId = response.conversation_id;
            storage.set('current_conversation_id', conversationId);
            updateConversationDisplay();
        }
        hideTypingIndicator();
        addMessageToUI(response.response, 'assistant');
        console.log('Token usage:', response.token_usage);
        if (chatLayout.classList.contains('sidebar-open')) {
            historyManager.loadConversations(false);
        }
    } catch (error) {
        hideTypingIndicator();
        console.error('Error:', error);
        toast.error(error.message || 'Failed to get response');
        addMessageToUI('Sorry, I encountered an error. Please try again.', 'error');
    } finally {
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

async function sendMessageStreaming(message) {
    const base = window.INSTANCE_BASE_PATH || '';
    const resp = await fetch(base + '/api/chat/stream', {
        method: 'POST',
        redirect: 'manual',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            conversation_id: conversationId,
            channel: 'webui'
        })
    });

    // Auth gateway returns 302 on expired sessions; fetch follows it converting
    // POST→GET, which then 405s because the route is POST-only. Detect this early
    // and redirect the whole page to re-login instead of surfacing a confusing 405.
    if (resp.type === 'opaqueredirect' || resp.status === 401 || resp.status === 403) {
        window.location.href = base + '/';
        return;
    }

    if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let toolTraceContainer = null;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            let event;
            try {
                event = JSON.parse(line.slice(6));
            } catch {
                continue;
            }

            if (event.type === 'iteration_start') {
                // Ensure we have a container for tool call cards
                if (!toolTraceContainer) {
                    toolTraceContainer = document.createElement('div');
                    toolTraceContainer.className = 'tool-trace-container';
                    // Insert before the typing indicator
                    const indicator = document.getElementById('typingIndicator');
                    if (indicator) {
                        chatMessages.insertBefore(toolTraceContainer, indicator);
                    } else {
                        chatMessages.appendChild(toolTraceContainer);
                    }
                }

            } else if (event.type === 'tool_call') {
                if (!toolTraceContainer) {
                    toolTraceContainer = document.createElement('div');
                    toolTraceContainer.className = 'tool-trace-container';
                    const indicator = document.getElementById('typingIndicator');
                    if (indicator) {
                        chatMessages.insertBefore(toolTraceContainer, indicator);
                    } else {
                        chatMessages.appendChild(toolTraceContainer);
                    }
                }
                renderToolCallCard(toolTraceContainer, event);
                chatMessages.scrollTop = chatMessages.scrollHeight;

            } else if (event.type === 'tool_result') {
                if (toolTraceContainer) {
                    updateToolCallCard(toolTraceContainer, event);
                }

            } else if (event.type === 'complete') {
                hideTypingIndicator();
                if (event.conversation_id) {
                    conversationId = event.conversation_id;
                    storage.set('current_conversation_id', conversationId);
                    updateConversationDisplay();
                }
                addMessageToUI(event.response, 'assistant');
                console.log('Token usage:', event.token_usage);
                if (chatLayout.classList.contains('sidebar-open')) {
                    historyManager.loadConversations(false);
                }
                messageInput.disabled = false;
                sendButton.disabled = false;
                messageInput.focus();

            } else if (event.type === 'error') {
                hideTypingIndicator();
                toast.error(event.error || 'Failed to get response');
                addMessageToUI('Sorry, I encountered an error. Please try again.', 'error');
                messageInput.disabled = false;
                sendButton.disabled = false;
                messageInput.focus();
            }
        }
    }
}

// Create a new tool call card in the trace container
function renderToolCallCard(container, event) {
    const card = document.createElement('div');
    card.className = 'tool-call-card running';
    card.dataset.tool = event.tool;

    // Build a short args summary (first key=value pair, truncated)
    let argsSummary = '';
    if (event.args && typeof event.args === 'object') {
        const entries = Object.entries(event.args);
        if (entries.length > 0) {
            const [k, v] = entries[0];
            const val = typeof v === 'string' ? v : JSON.stringify(v);
            argsSummary = `${k}: ${val}`;
            if (argsSummary.length > 80) argsSummary = argsSummary.slice(0, 77) + '…';
        }
    }

    card.innerHTML = `
        <span class="tool-call-icon">🔧</span>
        <span class="tool-call-body">
            <span class="tool-call-name">${escapeHtml(event.tool)}</span>
            ${argsSummary ? `<div class="tool-call-args">${escapeHtml(argsSummary)}</div>` : ''}
        </span>
        <span class="tool-call-status"><span class="tool-spinner"></span></span>
    `;
    container.appendChild(card);
}

// Update the most recent card for this tool with the result
function updateToolCallCard(container, event) {
    // Find the last running card for this tool
    const cards = container.querySelectorAll(`.tool-call-card[data-tool="${CSS.escape(event.tool)}"].running`);
    const card = cards[cards.length - 1];
    if (!card) return;

    card.classList.remove('running');
    card.classList.add(event.success ? 'done' : 'failed');

    const icon = card.querySelector('.tool-call-icon');
    if (icon) icon.textContent = event.success ? '✓' : '✗';

    const statusEl = card.querySelector('.tool-call-status');
    if (statusEl) statusEl.textContent = event.success ? 'done' : 'failed';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Configure marked once at module level
if (typeof marked !== 'undefined') {
    marked.use({ breaks: true, gfm: true });
}

function renderMarkdown(content) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
        return null;
    }
    return DOMPurify.sanitize(marked.parse(content));
}

// Add message to UI
function addMessageToUI(content, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (role === 'assistant') {
        const html = renderMarkdown(content);
        if (html !== null) {
            contentDiv.innerHTML = html;
        } else {
            contentDiv.textContent = content;
        }
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Typing indicator
function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant';
    indicator.id = 'typingIndicator';

    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

    indicator.appendChild(typingDiv);
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Start new conversation
function startNewConversation() {
    conversationId = null;
    storage.remove('current_conversation_id');
    conversationHistory = [];
    chatMessages.innerHTML = '';

    // Add welcome message
    addMessageToUI('Hello! I\'m your personal assistant. How can I help you today?', 'assistant');

    updateConversationDisplay();

    // Refresh sidebar to show new conversation will appear after first message
    historyManager.renderConversationList();

    toast.success('Started new conversation');
}

// Update conversation display
function updateConversationDisplay() {
    if (conversationIdDisplay) {
        if (conversationId) {
            conversationIdDisplay.textContent = `ID: ${conversationId.substring(0, 8)}...`;
        } else {
            conversationIdDisplay.textContent = 'New Conversation';
        }
    }
}

// Conversation History Manager
class ConversationHistoryManager {
    constructor() {
        this.conversations = [];
        this.currentPage = 0;
        this.pageSize = 20;
        this.isLoading = false;
        this.searchQuery = '';
        this.dateFilter = 'all';
        this.hasMore = true;
    }

    async loadConversations(append = false) {
        if (this.isLoading) return;

        this.isLoading = true;
        const offset = append ? this.conversations.length : 0;

        console.log('Loading conversations...', { append, offset, searchQuery: this.searchQuery, dateFilter: this.dateFilter });

        try {
            const params = new URLSearchParams({
                q: this.searchQuery,
                date_filter: this.dateFilter,
                limit: this.pageSize,
                offset: offset
            });

            const url = `/api/conversations/search?${params}`;
            console.log('Fetching:', url);
            const response = await api.get(url);
            console.log('Response:', response);

            if (append) {
                this.conversations = [...this.conversations, ...response.conversations];
            } else {
                this.conversations = response.conversations;
            }

            this.hasMore = response.has_more;
            console.log('Loaded conversations:', this.conversations.length, 'Has more:', this.hasMore);
            this.renderConversationList();
            this.updateLoadMoreButton();

        } catch (error) {
            console.error('Failed to load conversations:', error);
            toast.error('Failed to load conversation history');
        } finally {
            this.isLoading = false;
        }
    }

    renderConversationList() {
        const listContainer = document.getElementById('conversationList');

        if (this.isLoading && this.conversations.length === 0) {
            listContainer.innerHTML = '<div class="sidebar-loading">Loading conversations...</div>';
            return;
        }

        if (this.conversations.length === 0) {
            listContainer.innerHTML = '<div class="sidebar-empty">No conversations yet.<br>Start chatting to create one!</div>';
            return;
        }

        listContainer.innerHTML = '';
        this.conversations.forEach(conv => {
            const card = this.renderConversationCard(conv);
            listContainer.appendChild(card);
        });
    }

    renderConversationCard(conv) {
        const card = document.createElement('div');
        card.className = 'conversation-card';

        if (conv.conversation_id === conversationId) {
            card.classList.add('active');
        }

        if (conv.pinned) {
            card.classList.add('pinned');
        }

        // Header with title and pin button
        const header = document.createElement('div');
        header.className = 'conversation-card-header';

        const title = document.createElement('h4');
        title.className = 'conversation-title';
        title.textContent = conv.title || 'New Conversation';

        const pinBtn = document.createElement('button');
        pinBtn.className = 'pin-button';
        if (conv.pinned) {
            pinBtn.classList.add('pinned');
        }
        pinBtn.innerHTML = '★';
        pinBtn.title = conv.pinned ? 'Unpin' : 'Pin';
        pinBtn.onclick = (e) => {
            e.stopPropagation();
            this.togglePin(conv.conversation_id);
        };

        header.appendChild(title);
        header.appendChild(pinBtn);

        // Meta info
        const meta = document.createElement('div');
        meta.className = 'conversation-meta';

        const timestamp = document.createElement('span');
        timestamp.className = 'conversation-timestamp';
        timestamp.textContent = formatDateTime(conv.updated_at);

        const messageCount = document.createElement('span');
        messageCount.className = 'conversation-message-count';
        messageCount.textContent = `${conv.message_count || 0} messages`;

        meta.appendChild(timestamp);
        meta.appendChild(messageCount);

        // Preview
        const preview = document.createElement('div');
        preview.className = 'conversation-preview';
        preview.textContent = conv.last_message_preview || 'No messages yet';

        // Assemble card
        card.appendChild(header);
        card.appendChild(meta);
        card.appendChild(preview);

        // Click handler
        card.onclick = () => {
            this.switchConversation(conv.conversation_id);
        };

        return card;
    }

    async switchConversation(convId) {
        conversationId = convId;
        storage.set('current_conversation_id', conversationId);

        // Load conversation history
        await loadConversationHistory();

        // Update display
        updateConversationDisplay();

        // Update sidebar active state
        this.renderConversationList();

        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            this.toggleSidebar();
        }
    }

    async togglePin(convId) {
        try {
            const response = await api.post(`/api/conversations/${convId}/pin`);

            // Update local conversation
            const conv = this.conversations.find(c => c.conversation_id === convId);
            if (conv) {
                conv.pinned = response.pinned;
                conv.metadata = response.metadata;
            }

            // Re-sort and render
            await this.loadConversations(false);

            toast.success(response.pinned ? 'Conversation pinned' : 'Conversation unpinned');
        } catch (error) {
            console.error('Failed to toggle pin:', error);
            toast.error('Failed to update conversation');
        }
    }

    async searchConversations(query) {
        this.searchQuery = query;
        await this.loadConversations(false);
    }

    async filterByDate(filter) {
        this.dateFilter = filter;
        await this.loadConversations(false);
    }

    toggleSidebar() {
        const wasOpen = chatLayout.classList.contains('sidebar-open');
        chatLayout.classList.toggle('sidebar-open');
        const isNowOpen = chatLayout.classList.contains('sidebar-open');

        console.log('Toggling sidebar:', { wasOpen, isNowOpen, conversationCount: this.conversations.length });

        // Load conversations on first open
        if (isNowOpen && this.conversations.length === 0) {
            console.log('Loading conversations for first time...');
            this.loadConversations(false);
        }
    }

    updateLoadMoreButton() {
        if (loadMoreBtn) {
            loadMoreBtn.disabled = !this.hasMore || this.isLoading;
            loadMoreBtn.textContent = this.isLoading ? 'Loading...' : 'Load More';
        }
    }
}

// Initialize history manager
const historyManager = new ConversationHistoryManager();

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
