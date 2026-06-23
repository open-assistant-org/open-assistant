# Slack Integration Guide

This guide covers setting up the Slack integration for sending and receiving messages through a Slack workspace.

## Overview

The integration uses the **official Slack API** via a Slack Bot (App) you create in your workspace. The bot can:
- Receive messages via Socket Mode (outbound WebSocket) or HTTP webhooks
- Send messages to any channel it has been invited to
- Reply directly in the channel
- Be restricted to specific users

### Socket Mode vs HTTP Webhooks

| Feature | Socket Mode | HTTP Webhooks |
|---------|-------------|---------------|
| **Network Requirements** | Outbound only | Requires public URL |
| **Use Case** | Closed networks, development | Public servers, cloud deployments |
| **Configuration** | `slack.app_token` required | `slack.signing_secret` required |
| **Setup Complexity** | Simpler (no URL to expose) | Requires reverse proxy/tunnel |

**Recommendation:** Use Socket Mode if your app runs on a closed network or behind a firewall. Use HTTP webhooks if you have a public server.

## Prerequisites

- A Slack workspace where you have permission to install apps
- Access to [Slack API portal](https://api.slack.com/apps)

## Setup: Socket Mode (Recommended for Closed Networks)

Socket Mode establishes an **outbound WebSocket connection** from your app to Slack. This is ideal for:
- Closed networks with no inbound access
- Development environments
- Behind-firewall deployments

### Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Enter an App Name (e.g., "Open Assistant") and select your workspace
5. Click **Create App**

### Step 2: Configure Bot Permissions

1. In the left sidebar, go to **OAuth & Permissions**
2. Scroll down to **Scopes > Bot Token Scopes**
3. Add the following scopes:
   - `chat:write` - Send messages as the bot
   - `channels:read` - View basic channel info
   - `channels:history` - Read messages in public channels
   - `groups:read` - View basic info about private channels the bot is in
   - `groups:history` - Read messages in private channels the bot is in
   - `im:history` - Read direct messages to the bot
   - `im:read` - View basic DM info
   - `users:read` - View user info
   - `files:read` - Access file content shared in channels (required for media handling)

### Step 3: Enable Socket Mode (IMPORTANT: Do this FIRST!)

> **Important:** Enable Socket Mode BEFORE configuring Event Subscriptions. If you configure events first, Slack will require a public Request URL, which you don't need with Socket Mode.

1. In the left sidebar, go to **Socket Mode**
2. Toggle **Enable Socket Mode** to **ON**
3. The connection mode will switch from HTTP to WebSocket
4. You should see "Connection mode: Socket Mode" confirmed

### Step 4: Create App-Level Token

1. After enabling Socket Mode, you'll be prompted to create an App-Level Token
2. Enter a token name (e.g., "socket-mode-token")
3. Add the `connections:write` scope
4. Click **Generate**
5. Copy the **App-Level Token** (starts with `xapp-`) -- you will need this

### Step 5: Subscribe to Bot Events

> **Note:** With Socket Mode enabled, you won't need to enter a Request URL. If you see a Request URL field that's required, go back and make sure Socket Mode is enabled first.

1. In the left sidebar, go to **Event Subscriptions**
2. Toggle **Enable Events** to **ON**
3. With Socket Mode enabled, you should NOT see a Request URL requirement
4. Under **Subscribe to bot events**, add:
   - `message.im` - Direct messages to the bot (**required for DMs**)
   - `message.channels` - Messages in public channels (optional)
   - `message.groups` - Messages in private channels (optional)
5. Click **Save Changes**

### Step 6: Install the App to Your Workspace

1. In the left sidebar, go to **OAuth & Permissions**
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`) -- you will need this

### Step 7: Invite the Bot to Channels

In Slack, invite the bot to any channel where you want it to listen:
```
/invite @YourBotName
```

### Step 8: Configure in Open Assistant

1. Go to **Settings > Integrations > Slack**
2. Enable the Slack integration
3. Fill in:
   - **Bot Token**: The `xoxb-...` token from Step 6
   - **App-Level Token**: The `xapp-...` token from Step 4
   - **Default Channel**: The channel ID where the bot should send messages by default
   - **Allowed User IDs**: Your Slack user ID (optional but recommended for security)
4. Click **Save Settings**
5. Click **Test Connection** to verify

---

## Setup: HTTP Webhooks (Alternative)

Use this method if you have a public server and prefer traditional webhooks.

### Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Enter an App Name (e.g., "Open Assistant") and select your workspace
5. Click **Create App**

### Step 2: Configure Bot Permissions

1. In the left sidebar, go to **OAuth & Permissions**
2. Scroll down to **Scopes > Bot Token Scopes**
3. Add the following scopes:
   - `chat:write` - Send messages as the bot
   - `channels:read` - View basic channel info
   - `channels:history` - Read messages in public channels
   - `groups:read` - View basic info about private channels the bot is in
   - `groups:history` - Read messages in private channels the bot is in
   - `im:history` - Read direct messages to the bot
   - `im:read` - View basic DM info
   - `users:read` - View user info
   - `files:read` - Access file content shared in channels (required for media handling)

### Step 3: Install the App to Your Workspace

1. Scroll up to **OAuth Tokens for Your Workspace**
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`) -- you will need this

### Step 4: Get the Signing Secret

1. In the left sidebar, go to **Basic Information**
2. Scroll down to **App Credentials**
3. Copy the **Signing Secret** -- you will need this

### Step 5: Enable Events (for receiving messages)

1. In the left sidebar, go to **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Set the **Request URL** to:
   ```
   https://<your-app-url>/api/slack/webhook/events
   ```
   Slack will send a verification challenge. Make sure your app is running and publicly accessible (e.g., via a reverse proxy or tunnel like ngrok).
4. Under **Subscribe to bot events**, add:
   - `message.channels` - Messages in public channels
   - `message.groups` - Messages in private channels
   - `message.im` - Direct messages to the bot
5. Click **Save Changes**

### Step 6: Invite the Bot to Channels

In Slack, invite the bot to any channel where you want it to listen:
```
/invite @YourBotName
```

### Step 7: Configure in Open Assistant

1. Go to **Settings > Integrations > Slack**
2. Enable the Slack integration
3. Fill in:
   - **Bot Token**: The `xoxb-...` token from Step 3
   - **Signing Secret**: The signing secret from Step 4
   - **Default Channel**: The channel ID where the bot should send messages by default (find this in Slack by right-clicking a channel > "View channel details" > the ID at the bottom)
   - **Allowed User IDs** (optional): Comma-separated list of Slack user IDs that are allowed to interact with the bot. Leave empty to allow all users.
4. Click **Save Settings**
5. Click **Test Connection** to verify

## Configuration Options

### Bot Token

The Bot User OAuth Token (`xoxb-...`) authenticates API requests. Found under **OAuth & Permissions** in your Slack app settings.

### Signing Secret

Used to verify that incoming webhook requests are genuinely from Slack. Found under **Basic Information > App Credentials**.

### App-Level Token

Required for **Socket Mode**. The App-Level Token (`xapp-...`) establishes the WebSocket connection. Follow the Socket Mode setup steps above to create this token.

### Default Channel

The channel ID where the bot sends messages when no specific channel is provided. To find a channel ID:
1. Open Slack
2. Right-click the channel name
3. Click **View channel details**
4. The Channel ID is shown at the bottom of the details panel (e.g., `C01ABCDEF12`)

### Allowed User IDs

Restrict which Slack users can interact with the bot. To find a user ID:
1. Click on a user's profile in Slack
2. Click the **...** (More) button
3. Click **Copy member ID**

Leave this field empty to allow all workspace members.

## How Messages Work

### Socket Mode (Default)

1. The app establishes an outbound WebSocket connection to Slack on startup
2. A user sends a message in a channel where the bot is present (or via DM)
3. Slack pushes the event through the WebSocket
4. The bot processes the message through Open Assistant's message handler
5. The response is sent back as a threaded reply in the same channel

### HTTP Webhooks (Alternative)

1. A user sends a message in a channel where the bot is present (or via DM)
2. Slack sends the event to your webhook URL (`/api/slack/webhook/events`)
3. The bot processes the message through Open Assistant's message handler
4. The response is sent back as a threaded reply in the same channel

## Troubleshooting

### Bot doesn't respond to messages

**For Socket Mode:**
- Check application logs for "Slack Socket Mode client started"
- Verify the App-Level Token (`xapp-...`) is correct and has `connections:write` scope
- Ensure Socket Mode is enabled in your Slack app settings
- Check that Event Subscriptions are enabled with the correct bot events subscribed

**For HTTP Webhooks:**
- Verify the bot is invited to the channel (`/invite @BotName`)
- Check that Event Subscriptions are enabled and the Request URL is verified
- Verify the Bot Token and Signing Secret are correct in Settings

**For Both:**
- Check the application logs for errors
- Ensure the allowed user IDs list doesn't exclude the user (or leave it empty)

### "not_authed" or "invalid_auth" errors

- The Bot Token may be invalid or revoked
- Reinstall the app to your workspace to get a new token

### "channel_not_found" when sending messages

- The bot must be a member of the channel
- Ensure you're using the Channel ID (e.g., `C01ABCDEF12`), not the channel name

### Webhook URL verification fails

- Make sure your app is publicly accessible at the URL you configured
- The `/api/slack/webhook/events` endpoint must be reachable from Slack's servers
- For local development, use a tunnel like [ngrok](https://ngrok.com/): `ngrok http 8080`

### Messages are duplicated

- Slack may retry events if your server doesn't respond quickly enough. The bot processes messages in the background and responds with a 200 immediately, which should prevent retries.

## Security Considerations

- **Bot Token**: Treat it like a password. It grants access to your workspace.
- **Signing Secret**: Used to verify webhook requests. Keep it secret.
- **Allowed Users**: Restrict access to trusted users when the bot has access to sensitive tools.
- **Channel Permissions**: Only invite the bot to channels where it should be active.

## Limitations

- The bot responds in the channel, not as top-level channel messages
- Socket Mode and HTTP webhooks cannot be used simultaneously for receiving events - choose one based on your network setup

## File Handling

The `files:read` bot scope is required for the bot to access file content shared in channels. File content can be downloaded using the `download_file` method on the Slack client, which uses the bot token for authentication.

Media processing (image analysis, OCR, transcription) is not handled by the Slack client itself — it depends on other integrations (vision LLM, Mistral OCR, Whisper) being enabled.

## Resources

- **Slack API Documentation**: [https://api.slack.com/](https://api.slack.com/)
- **Slack Bot Scopes Reference**: [https://api.slack.com/scopes](https://api.slack.com/scopes)
- **Events API Guide**: [https://api.slack.com/events-api](https://api.slack.com/events-api)
- **Slack SDK for Python**: [https://slack.dev/python-slack-sdk/](https://slack.dev/python-slack-sdk/)

---

**Last Updated**: February 2026
