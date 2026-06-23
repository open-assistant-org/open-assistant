# WhatsApp Integration Guide

This guide covers setting up WhatsApp integration for sending and receiving messages.

## Overview

The WhatsApp integration uses a **Node.js bridge service** that runs alongside the main Python application. The bridge uses `whatsapp-web.js` to automate WhatsApp Web. The Python application communicates with the bridge via HTTP.

**Architecture**:
```
Python App (WhatsAppClient)
    ↓ HTTP (localhost:3001)
Node.js Bridge (whatsapp-web.js)
    ↓ WebSocket
WhatsApp Web
```

## ⚠️ Important Notice

This integration uses **whatsapp-web.js**, an **unofficial** WhatsApp API that automates WhatsApp Web.

**Disclaimer**:
- This is NOT an official WhatsApp API
- Use at your own risk
- WhatsApp may block accounts that violate their Terms of Service
- Recommended for personal use only, not for business/spam

## Prerequisites

- WhatsApp account
- Phone with WhatsApp installed
- Node.js installed (for the bridge service)

## How It Works

The integration uses whatsapp-web.js to:
1. Simulate a WhatsApp Web session
2. Authenticate via QR code (like logging into WhatsApp Web)
3. Send/receive messages through the web interface

The Python `WhatsAppClient` delegates all WhatsApp operations to the Node.js bridge.

## Bridge Service Setup

The bridge service must be running separately:

```bash
cd whatsapp-bridge
npm install
node index.js
```

The bridge defaults to `http://localhost:3001`. Update the bridge URL in settings if you run it on a different port.

## Python Client Operations

The Python `WhatsAppClient` exposes the following operations:

| Method | Description |
|--------|-------------|
| `get_status()` | Returns WhatsApp connection status and QR code if not connected |
| `is_ready()` | Returns `True` if WhatsApp is connected and ready to send/receive |
| `send_message(phone_number, message)` | Send a text message to a phone number |
| `configure_webhook(webhook_url)` | Set a webhook URL to receive incoming messages |
| `test_connection()` | Returns `True` if the bridge is reachable and WhatsApp is ready |

### Sending a Message

```python
from src.integrations.whatsapp import WhatsAppClient

client = WhatsAppClient(bridge_url="http://localhost:3001")

if client.is_ready():
    client.send_message(
        phone_number="+14155551234",
        message="Hello from Open Assistant!"
    )
```

### Checking Status

```python
status = client.get_status()
# Returns: {"ready": True, "qr_code": None, ...}
# If not connected: {"ready": False, "qr_code": "data:image/png;base64,..."}
```

## Session Management

### Session Storage

WhatsApp session data is stored by the Node.js bridge in its session directory. This includes:
- Authentication tokens
- Browser session data

**Important**: Keep this directory secure and backed up.

### Session Expiration

Sessions may expire if:
- WhatsApp detects suspicious activity
- You log out from WhatsApp Web
- Long period of inactivity
- WhatsApp security updates

If expired, you'll need to scan the QR code again.

### Multiple Devices

To use multiple Open Assistant instances with the same WhatsApp account:
- Each instance needs its own Node.js bridge with its own session directory
- WhatsApp supports up to 4 linked devices
- Each will require QR code authentication

## Configuration Options

### Bridge URL

The URL of the running Node.js bridge service:

```
http://localhost:3001  # default
```

### Phone Number Format

When sending messages, always include country code:
```
✅ +14155551234
❌ 4155551234
❌ +1 (415) 555-1234
❌ +1-415-555-1234
```

## Troubleshooting

### Bridge Connection Error

- Check that the Node.js bridge service is running
- Verify the bridge URL in settings matches your bridge configuration
- Check that port 3001 is not blocked by a firewall

### "Connection Lost"

- Check internet connection
- Verify WhatsApp is working on your phone
- Check if you logged out from WhatsApp Web
- Try restarting the Node.js bridge service

### Messages Not Sending

- Verify the integration is enabled
- Check the recipient's number format
- Ensure you're connected (check `is_ready()`)
- Review rate limits

## Rate Limits & Best Practices

### Avoid Spam Behavior
WhatsApp monitors for spam:
- Don't send bulk messages
- Add delays between messages
- Don't message non-contacts excessively
- Respect user preferences

### Message Limits
Unofficial limits (not documented by WhatsApp):
- ~15-20 messages per minute
- ~500 messages per day to non-contacts
- No hard limit for existing conversations

### Best Practices
- ✅ Use for personal automation
- ✅ Message contacts only
- ✅ Respect rate limits
- ✅ Monitor for warnings
- ❌ Don't spam
- ❌ Don't send marketing messages
- ❌ Don't scrape data

## Official Alternative

For business use, consider **WhatsApp Business API**:
- Official, supported by Meta
- Higher rate limits
- Business features
- Requires approval
- Paid service

Learn more: [WhatsApp Business Platform](https://business.whatsapp.com/products/business-platform)

## Security Considerations

### Session Security
- Session directory contains authentication tokens
- Keep it secure (don't commit to Git)
- Back it up safely
- Use encryption for backups

### Data Privacy
- Messages are processed by whatsapp-web.js
- Local processing only (no third-party servers)
- End-to-end encryption is maintained
- Session data stored locally

### Account Safety
- Use for personal automation only
- Don't share session files
- Monitor account for suspicious activity
- Consider using a secondary number for testing

## Limitations

**Current Limitations**:
- Cannot make voice/video calls
- No automatic media processing in the Python client (voice transcription, image analysis, PDF extraction depend on other integrations being enabled)
- May not support newest WhatsApp features immediately
- Unofficial API may break with WhatsApp updates
- No support guarantee

**Not Recommended For**:
- Business critical applications
- High-volume messaging
- Customer support
- Marketing campaigns
- Data scraping

## Resources

- **whatsapp-web.js**: [GitHub Repository](https://github.com/pedroslopez/whatsapp-web.js)
- **WhatsApp Terms**: [Terms of Service](https://www.whatsapp.com/legal/terms-of-service)
- **WhatsApp Business API**: [Official Platform](https://business.whatsapp.com/)

## Need Help?

If you encounter issues:
1. Check the application logs
2. Review whatsapp-web.js documentation
3. Verify your WhatsApp account is active
4. Try deleting the Node.js bridge session and re-authenticate

---

**Last Updated**: March 2026
