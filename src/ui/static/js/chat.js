// Chat functionality with conversation persistence

let conversationId = storage.get('current_conversation_id');
let conversationHistory = [];

// ── File attachment state ──────────────────────────────────────────────────
// Each entry: { filename, path, size, content_type, uploading }
let attachedFiles = [];

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
const fileInput = document.getElementById('fileInput');
const attachButton = document.getElementById('attachButton');
const attachmentChips = document.getElementById('attachmentChips');

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

    // File attachment
    if (attachButton && fileInput) {
        attachButton.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelection);
    }
}

// ── File upload helpers ────────────────────────────────────────────────────

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderAttachmentChips() {
    if (!attachmentChips) return;
    if (attachedFiles.length === 0) {
        attachmentChips.style.display = 'none';
        attachmentChips.innerHTML = '';
        return;
    }
    attachmentChips.style.display = 'flex';
    attachmentChips.innerHTML = '';
    attachedFiles.forEach((f, idx) => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip' + (f.uploading ? ' uploading' : '');
        chip.title = f.filename;

        const icon = document.createElement('span');
        if (f.uploading) {
            icon.textContent = '⏳';
        } else if (f.image_base64) {
            icon.textContent = '🖼️';
        } else if (f.ocr_text || f.content_type === 'application/pdf' || (f.filename && f.filename.toLowerCase().endsWith('.pdf'))) {
            icon.textContent = '📑';
        } else {
            icon.textContent = '📄';
        }

        const name = document.createElement('span');
        name.className = 'attachment-chip-name';
        name.textContent = f.filename;

        const size = document.createElement('span');
        size.className = 'attachment-chip-size';
        size.textContent = f.size != null ? formatFileSize(f.size) : '';

        const removeBtn = document.createElement('button');
        removeBtn.className = 'attachment-chip-remove';
        removeBtn.textContent = '×';
        removeBtn.title = 'Remove attachment';
        removeBtn.setAttribute('aria-label', `Remove ${f.filename}`);
        removeBtn.addEventListener('click', () => {
            attachedFiles.splice(idx, 1);
            renderAttachmentChips();
        });

        chip.appendChild(icon);
        chip.appendChild(name);
        if (!f.uploading) chip.appendChild(size);
        chip.appendChild(removeBtn);
        attachmentChips.appendChild(chip);
    });
}

async function handleFileSelection(event) {
    const files = Array.from(event.target.files || []);
    // Reset the input so the same file can be re-selected if needed
    fileInput.value = '';
    if (files.length === 0) return;

    for (const file of files) {
        // Add a placeholder chip while uploading
        const placeholder = { filename: file.name, path: null, size: file.size, uploading: true };
        attachedFiles.push(placeholder);
        renderAttachmentChips();

        try {
            const formData = new FormData();
            formData.append('file', file);

            const base = window.INSTANCE_BASE_PATH || '';
            const resp = await fetch(base + '/api/upload', {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `Upload failed (${resp.status})`);
            }

            const data = await resp.json();
            // Replace placeholder with resolved file info
            const idx = attachedFiles.indexOf(placeholder);
            if (idx !== -1) {
                attachedFiles[idx] = {
                    filename: data.filename,
                    path: data.path,
                    size: data.size,
                    content_type: data.content_type,
                    uploading: false,
                    // Image: backend returns base64 so we can send it to the vision path
                    image_base64: data.image_base64 || null,
                    image_mimetype: data.image_mimetype || null,
                    // PDF: backend returns OCR text when Mistral OCR is configured
                    ocr_text: data.ocr_text || null,
                    ocr_available: data.ocr_available ?? null,
                };
            }
        } catch (err) {
            // Remove failed placeholder
            const idx = attachedFiles.indexOf(placeholder);
            if (idx !== -1) attachedFiles.splice(idx, 1);
            toast.error(`Failed to upload "${file.name}": ${err.message}`);
        }

        renderAttachmentChips();
    }
}

/**
 * Build a context prefix to inject into the message so the LLM knows about
 * any non-image, non-OCR attachments (i.e. files that the LLM must read via
 * tools like python_execute).
 *
 * Images are passed separately via image_base64/image_mimetype in the request
 * body and don't need a text mention here.
 *
 * PDFs that were successfully OCR'd have their text injected inline instead of
 * a file-path reference.
 */
function buildFileContext() {
    const ready = attachedFiles.filter(f => !f.uploading && f.path);
    if (ready.length === 0) return '';

    const parts = [];

    // ── OCR'd PDFs: inject extracted text inline ────────────────────────────
    const ocrFiles = ready.filter(f => f.ocr_text);
    for (const f of ocrFiles) {
        parts.push(
            `[The user attached "${f.filename}" (PDF, ${formatFileSize(f.size)}). ` +
            `The following text was extracted from it via OCR:]\n` +
            `\`\`\`\n${f.ocr_text}\n\`\`\``
        );
    }

    // ── PDFs without OCR: fall back to file-path reference ──────────────────
    const pdfNoOcr = ready.filter(
        f => (f.content_type === 'application/pdf' || f.filename.toLowerCase().endsWith('.pdf'))
             && !f.ocr_text
    );
    if (pdfNoOcr.length > 0) {
        const lines = pdfNoOcr.map(f =>
            `- "${f.filename}" → ${f.path} (PDF, ${formatFileSize(f.size)})`
        );
        parts.push(
            `[The user attached the following PDF(s). OCR is not configured, ` +
            `so the files are available at the paths below — use python_execute ` +
            `or analyze_content to read them:]\n` + lines.join('\n')
        );
    }

    // ── Other non-image files: file-path reference ───────────────────────────
    const otherFiles = ready.filter(
        f => !f.image_base64
             && f.content_type !== 'application/pdf'
             && !f.filename.toLowerCase().endsWith('.pdf')
             && !f.ocr_text
    );
    if (otherFiles.length > 0) {
        const lines = otherFiles.map(f =>
            `- "${f.filename}" → ${f.path} (${f.content_type || 'unknown type'}, ${formatFileSize(f.size)})`
        );
        parts.push(
            `[The user attached the following file(s). ` +
            `They are stored on the local filesystem and can be read with available ` +
            `tools such as python_execute or analyze_content:]\n` + lines.join('\n')
        );
    }

    // ── Images: brief mention so the LLM knows it received one ──────────────
    const images = ready.filter(f => f.image_base64);
    if (images.length > 0) {
        const names = images.map(f => `"${f.filename}"`).join(', ');
        parts.push(`[The user attached the following image(s): ${names}. ` +
                   `The image content is provided directly in this message.]`);
    }

    return parts.length > 0 ? parts.join('\n\n') + '\n\n' : '';
}

/**
 * Return the first image attachment's base64/mimetype, if any.
 * handle_message currently supports one image per turn.
 */
function getImageAttachment() {
    const img = attachedFiles.find(f => !f.uploading && f.image_base64);
    if (!img) return null;
    return { image_base64: img.image_base64, image_mimetype: img.image_mimetype };
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
    // Require either a text message or at least one uploaded file
    const hasFiles = attachedFiles.some(f => !f.uploading && f.path);
    if (!message && !hasFiles) return;

    // Block send while any file is still uploading
    if (attachedFiles.some(f => f.uploading)) {
        toast.error('Please wait for all files to finish uploading.');
        return;
    }

    // Capture image before clearing the list
    const imageAttachment = getImageAttachment();

    // Build the full message that gets sent to the LLM (file context + user text)
    const fileContext = buildFileContext();
    const fullMessage = fileContext + (message || '(No additional message — please analyze the attached file(s).)');

    // Show the user-facing bubble with just the text they typed (+ file list if any)
    const displayedFiles = attachedFiles.filter(f => !f.uploading && f.path);
    if (displayedFiles.length > 0) {
        addMessageToUI(message || '(See attached file(s))', 'user', displayedFiles);
    } else {
        addMessageToUI(message, 'user');
    }
    messageInput.value = '';

    // Clear attachments now that they've been included in the message
    attachedFiles = [];
    renderAttachmentChips();

    messageInput.disabled = true;
    sendButton.disabled = true;
    if (attachButton) attachButton.disabled = true;
    showTypingIndicator();

    // Streaming path (modern browsers)
    if (typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined') {
        try {
            await sendMessageStreaming(fullMessage, imageAttachment);
        } catch (error) {
            hideTypingIndicator();
            console.error('Streaming error:', error);
            toast.error(error.message || 'Failed to get response');
            addMessageToUI('Sorry, I encountered an error. Please try again.', 'error');
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            if (attachButton) attachButton.disabled = false;
            messageInput.focus();
        }
        return;
    }

    // Fallback: plain POST (no streaming)
    try {
        const response = await api.post('/api/chat', {
            message: fullMessage,
            conversation_id: conversationId,
            channel: 'webui',
            ...(imageAttachment || {}),
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
        if (attachButton) attachButton.disabled = false;
        messageInput.focus();
    }
}

async function sendMessageStreaming(message, imageAttachment) {
    const base = window.INSTANCE_BASE_PATH || '';
    const resp = await fetch(base + '/api/chat/stream', {
        method: 'POST',
        redirect: 'manual',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            conversation_id: conversationId,
            channel: 'webui',
            ...(imageAttachment || {}),
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
// attachments: optional array of { filename, path, size } for user messages
function addMessageToUI(content, role, attachments) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Render file attachment banners for user messages
    if (role === 'user' && attachments && attachments.length > 0) {
        const banner = document.createElement('div');
        banner.className = 'attachment-banner';
        banner.innerHTML = attachments
            .map(f => `📎 <strong>${escapeHtml(f.filename)}</strong> (${formatFileSize(f.size)})`)
            .join('<br>');
        contentDiv.appendChild(banner);
    }

    if (role === 'assistant') {
        const html = renderMarkdown(content);
        const textNode = document.createElement('div');
        if (html !== null) {
            textNode.innerHTML = html;
        } else {
            textNode.textContent = content;
        }
        contentDiv.appendChild(textNode);
    } else {
        if (content) {
            const textNode = document.createTextNode(content);
            contentDiv.appendChild(textNode);
        }
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
    attachedFiles = [];
    renderAttachmentChips();
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
