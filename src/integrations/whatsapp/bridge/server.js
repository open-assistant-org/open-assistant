/**
 * WhatsApp Web.js Bridge Server
 *
 * Provides a REST API bridge between Python and whatsapp-web.js
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const bodyParser = require('body-parser');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const { CHROMIUM_ARGS } = require('./launch-args');

const app = express();
app.use(bodyParser.json({ limit: '50mb' }));

const PORT = process.env.WHATSAPP_BRIDGE_PORT || 3001;
const SESSION_PATH = process.env.WHATSAPP_SESSION_DIR || './whatsapp_session';
const WEBHOOK_URL = process.env.WHATSAPP_WEBHOOK_URL || 'http://localhost:8080/api/whatsapp/webhook/incoming';
const CHROMIUM_PATH = process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium-browser';

/**
 * Clean up stale Chromium lock files that prevent browser launch.
 * This happens when Chrome doesn't shut down cleanly (e.g., container crash).
 */
function cleanupStaleLockFiles(sessionPath) {
    const lockFiles = ['SingletonLock', 'SingletonCookie', 'SingletonSocket'];

    if (!fs.existsSync(sessionPath)) {
        return;
    }

    // Recursively find and remove lock files
    function cleanDirectory(dir) {
        if (!fs.existsSync(dir)) return;

        try {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    cleanDirectory(fullPath);
                } else if (lockFiles.includes(entry.name)) {
                    try {
                        fs.unlinkSync(fullPath);
                        console.log(`🧹 Removed stale lock file: ${fullPath}`);
                    } catch (e) {
                        console.warn(`⚠️  Could not remove lock file ${fullPath}:`, e.message);
                    }
                }
            }
        } catch (e) {
            console.warn(`⚠️  Could not read directory ${dir}:`, e.message);
        }
    }

    // Search the session path directly - LocalAuth with dataPath stores
    // the Chromium profile at {dataPath}/session/, not {dataPath}/.wwebjs_auth/
    cleanDirectory(sessionPath);
}

// Clean up any stale lock files before initializing
console.log('🧹 Checking for stale browser lock files...');
cleanupStaleLockFiles(SESSION_PATH);

// Initialize WhatsApp client
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: SESSION_PATH
    }),
    puppeteer: {
        headless: true,
        executablePath: CHROMIUM_PATH,
        args: CHROMIUM_ARGS
    }
});

let isReady = false;
let qrCodeData = null;
let webhookUrl = WEBHOOK_URL; // Auto-configure from environment

// QR Code event
client.on('qr', (qr) => {
    console.log('QR Code received');
    qrCodeData = qr;

    // Display QR code in terminal
    qrcode.generate(qr, { small: true });

    console.log('\n📱 Scan this QR code with WhatsApp on your phone');
    console.log('Go to: WhatsApp > Settings > Linked Devices > Link a Device\n');
});

// Ready event
client.on('ready', () => {
    console.log('✅ WhatsApp client is ready!');
    isReady = true;
    qrCodeData = null;
});

// Authenticated event
client.on('authenticated', () => {
    console.log('✅ WhatsApp authenticated');
});

// Authentication failure
client.on('auth_failure', (msg) => {
    console.error('❌ Authentication failed:', msg);
    isReady = false;
});

// Disconnected event
client.on('disconnected', (reason) => {
    console.log('⚠️  WhatsApp disconnected:', reason);
    isReady = false;
});

// Message received event
client.on('message', async (message) => {
    console.log('📨 Message received:', message.from, message.body, 'hasMedia:', message.hasMedia);

    // Forward to webhook if configured
    if (webhookUrl) {
        try {
            const payload = {
                from: message.from,
                body: message.body || '',
                timestamp: message.timestamp,
                hasMedia: message.hasMedia
            };

            // Download media if present
            if (message.hasMedia) {
                try {
                    console.log('📎 Downloading media from message...');
                    const media = await message.downloadMedia();
                    if (media) {
                        payload.mediaData = media.data;  // base64-encoded
                        payload.mimetype = media.mimetype;
                        payload.filename = media.filename || null;
                        console.log(`📎 Media downloaded: ${media.mimetype}, size: ${media.data.length} chars (base64)`);
                    }
                } catch (mediaError) {
                    console.error('Failed to download media:', mediaError.message);
                    // Still forward the message without media data
                }
            }

            const fetch = (await import('node-fetch')).default;
            await fetch(webhookUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (error) {
            console.error('Failed to forward message to webhook:', error);
        }
    }
});

// Initialize client with error handling
console.log('🔄 Initializing WhatsApp client...');
client.initialize().catch((error) => {
    console.error('❌ Failed to initialize WhatsApp client:', error);
    console.error('Stack trace:', error.stack);
    // Don't exit immediately - let supervisord handle retries
    // The server will still be running but not ready
});

// ============================================================================
// API ENDPOINTS
// ============================================================================

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'whatsapp-bridge',
        ready: isReady
    });
});

// Get status
app.get('/status', (req, res) => {
    res.json({
        ready: isReady,
        has_qr: qrCodeData !== null,
        qr_code: qrCodeData
    });
});

// Send message
app.post('/send', async (req, res) => {
    try {
        if (!isReady) {
            return res.status(503).json({
                error: 'WhatsApp client not ready',
                message: 'Please authenticate first'
            });
        }

        const { phone_number, message } = req.body;

        if (!phone_number || !message) {
            return res.status(400).json({
                error: 'Missing required fields',
                message: 'phone_number and message are required'
            });
        }

        // Format phone number or use existing WhatsApp ID
        let chatId;
        if (phone_number.includes('@')) {
            // Already has WhatsApp suffix (@c.us or @lid), use as-is
            chatId = phone_number;
            console.log(`📱 Using full WhatsApp ID: ${chatId}`);
        } else {
            // Format phone number (remove + and spaces) and append @c.us
            const formattedNumber = phone_number.replace(/[^0-9]/g, '');
            chatId = formattedNumber + '@c.us';
            console.log(`📱 Formatted to: ${chatId}`);
        }

        // Send message
        console.log(`📨 Sending to chatId: ${chatId}`);

        // For @lid contacts, try to get the chat first
        try {
            const chat = await client.getChatById(chatId);
            await chat.sendMessage(message);
            console.log(`✅ Message sent via chat object`);
        } catch (chatError) {
            console.log(`⚠️  Chat object method failed, trying direct send: ${chatError.message}`);
            // Fallback to direct send
            await client.sendMessage(chatId, message);
        }

        console.log(`✅ Message sent to ${phone_number}`);

        res.json({
            success: true,
            message: 'Message sent successfully',
            to: phone_number
        });

    } catch (error) {
        console.error('Failed to send message:', error);
        res.status(500).json({
            error: 'Failed to send message',
            message: error.message
        });
    }
});

// Configure webhook
app.post('/webhook', (req, res) => {
    try {
        const { url } = req.body;

        if (!url) {
            return res.status(400).json({
                error: 'Missing webhook URL'
            });
        }

        webhookUrl = url;
        console.log('📡 Webhook configured:', webhookUrl);

        res.json({
            success: true,
            message: 'Webhook configured',
            webhook_url: webhookUrl
        });

    } catch (error) {
        res.status(500).json({
            error: 'Failed to configure webhook',
            message: error.message
        });
    }
});

// Start server
app.listen(PORT, () => {
    console.log(`🚀 WhatsApp bridge server running on http://localhost:${PORT}`);
    console.log(`📁 Session directory: ${SESSION_PATH}`);
    console.log(`📡 Webhook configured: ${webhookUrl}`);
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n⏹️  Shutting down WhatsApp bridge...');
    await client.destroy();
    process.exit(0);
});
