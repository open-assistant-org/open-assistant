// Talk page: a voice conversation with the assistant through an ElevenLabs agent.
//
// Everything connects out from this browser: the voice session goes to
// ElevenLabs (via a signed URL our server fetched with the API key), and the
// agent's *client tools* run here and call this app on the same origin. No
// connection from ElevenLabs into the assistant is needed.

(function () {
    const base = window.INSTANCE_BASE_PATH || '';
    const els = {
        mic: document.getElementById('talkMic'),
        state: document.getElementById('talkState'),
        error: document.getElementById('talkError'),
        transcript: document.getElementById('talkTranscript'),
        insecure: document.getElementById('talkInsecure'),
        notConfigured: document.getElementById('talkNotConfigured'),
    };

    let conversation = null;
    let conversationId = null;
    let connecting = false;
    let pendingTools = 0;
    let mode = 'listening';
    let endReported = false;
    let unavailable = ''; // why the page can't be used (shown instead of the idle hint)

    function addLine(role, text) {
        if (!text) return;
        const line = document.createElement('div');
        line.className = `talk-line ${role}`;
        line.textContent = text;
        els.transcript.appendChild(line);
        els.transcript.scrollTop = els.transcript.scrollHeight;
    }

    function setError(message) {
        els.error.textContent = message || '';
    }

    function render() {
        const active = !!conversation;
        els.mic.classList.toggle('active', active);
        els.mic.classList.toggle('listening', active && mode === 'listening' && !pendingTools);
        els.mic.classList.toggle('speaking', active && mode === 'speaking');
        els.mic.setAttribute('aria-pressed', String(active));
        els.mic.setAttribute('aria-label', active ? 'End conversation' : 'Start conversation');
        if (unavailable) {
            els.state.textContent = unavailable;
        } else if (connecting) {
            els.state.textContent = 'Connecting…';
        } else if (!active) {
            els.state.textContent = 'Tap the microphone to start';
        } else if (pendingTools) {
            els.state.textContent = 'Working on it…';
        } else {
            els.state.textContent = mode === 'speaking' ? 'Speaking…' : 'Listening…';
        }
    }

    // --- client tools: forwarded to this app on the same origin --------------

    async function callApp(path, payload) {
        pendingTools += 1;
        render();
        try {
            const result = await api.post(path, payload);
            return JSON.stringify(result);
        } catch (err) {
            console.error('Voice tool failed:', err);
            return JSON.stringify({
                status: 'error',
                answer: 'Sorry, I could not reach the assistant just now.',
            });
        } finally {
            pendingTools -= 1;
            render();
        }
    }

    const clientTools = {
        ask_assistant: (params) => callApp('/api/elevenlabs/voice/ask', {
            request: String((params && params.request) || ''),
            conversation_id: conversationId,
        }),
        check_assistant_result: (params) => callApp('/api/elevenlabs/voice/result', {
            job_id: String((params && params.job_id) || ''),
        }),
    };

    // --- session lifecycle ----------------------------------------------------

    function reportEnd() {
        // Tell the server the call is over (flushes pending results, stores the
        // transcript). sendBeacon survives page close; fall back to fetch.
        if (endReported || !conversationId) return;
        endReported = true;
        const url = `${base}/api/elevenlabs/voice/end`;
        const body = JSON.stringify({ conversation_id: conversationId });
        let sent = false;
        try {
            sent = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
        } catch (e) {
            sent = false;
        }
        if (!sent) {
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body,
                keepalive: true,
            }).catch(() => {});
        }
    }

    function resetSession() {
        conversation = null;
        pendingTools = 0;
        mode = 'listening';
        render();
    }

    async function start() {
        setError('');
        connecting = true;
        endReported = false;
        conversationId = null;
        els.mic.disabled = true;
        render();
        try {
            // Ask for the microphone first so a permission prompt isn't swallowed by the connect.
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach((track) => track.stop());

            const { signed_url: signedUrl } = await api.post('/api/elevenlabs/session', {});
            conversation = await ElevenLabsClient.Conversation.startSession({
                signedUrl,
                connectionType: 'websocket',
                clientTools,
                libsampleratePath: `${base}/static/js/libsamplerate.worklet.js`,
                onConnect: ({ conversationId: id }) => {
                    conversationId = id;
                },
                onMessage: ({ role, message }) => addLine(role === 'user' ? 'user' : 'agent', message),
                onModeChange: ({ mode: next }) => {
                    mode = next;
                    render();
                },
                onError: (message) => setError(String(message || 'Voice connection error')),
                onDisconnect: (details) => {
                    reportEnd();
                    resetSession();
                    if (details && details.reason === 'error') {
                        setError(details.message || 'The voice connection was lost.');
                    }
                    addLine('system', 'Conversation ended');
                },
            });
            conversationId = conversationId || conversation.getId();
            addLine('system', 'Conversation started');
        } catch (err) {
            console.error('Could not start voice session:', err);
            const denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
            setError(denied
                ? 'Microphone access was blocked. Allow it in the browser and try again.'
                : (err && err.message) || 'Could not start the conversation.');
            conversation = null;
        } finally {
            connecting = false;
            els.mic.disabled = false;
            render();
        }
    }

    async function stop() {
        const current = conversation;
        if (!current) return;
        try {
            await current.endSession();
        } catch (err) {
            console.error('Error ending session:', err);
            reportEnd();
            resetSession();
        }
    }

    els.mic.addEventListener('click', () => {
        if (connecting) return;
        (conversation ? stop() : start());
    });

    // Closing the tab ends the call; make sure the server hears about it.
    window.addEventListener('pagehide', () => {
        if (conversation) reportEnd();
    });

    // --- setup ----------------------------------------------------------------

    async function init() {
        if (!window.isSecureContext || !navigator.mediaDevices) {
            els.insecure.hidden = false;
            els.mic.disabled = true;
        }
        try {
            const status = await api.get('/api/elevenlabs/status');
            if (!status.enabled) {
                unavailable = 'ElevenLabs voice is turned off. Enable it in Settings → Integrations.';
                els.mic.disabled = true;
            } else if (!status.configured) {
                els.notConfigured.hidden = false;
                els.mic.disabled = true;
            }
        } catch (err) {
            setError('Could not read the voice settings.');
            els.mic.disabled = true;
        }
        render();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
