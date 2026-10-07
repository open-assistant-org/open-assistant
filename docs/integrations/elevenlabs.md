# ElevenLabs Voice

Talk to your assistant by voice from the web UI. When the integration is enabled, a
**Talk** item (microphone icon) appears in the navbar. The page runs a conversation
with an [ElevenLabs](https://elevenlabs.io) voice agent, and the agent hands real work
to the assistant. Requests run through the same skills, tools and memory as Slack and
WhatsApp, under the channel name `elevenlabs`.

## Everything connects out

Nothing has to reach your instance from the internet:

```
Talk page (your browser) ──WebSocket, outbound──▶ ElevenLabs agent (fast LLM + voice)
   │  client tool: ask_assistant / check_assistant_result
   ▼  same-origin request
Open Assistant /api/elevenlabs/voice/*  ──▶  MessageHandler (channel "elevenlabs")

Open Assistant ──HTTPS, outbound──▶ api.elevenlabs.io   (session URL before the call,
                                                          transcript after it)
```

- The voice session is opened by the browser, using a short-lived signed URL that
  Open Assistant fetches with your API key. The key never reaches the browser.
- The agent's tools are **client tools**: they run in the Talk page, which forwards them
  to Open Assistant on the same origin.
- The voice model inside ElevenLabs handles small talk instantly. Real work goes to the
  assistant, so latency for those requests is that of a normal chat turn. The agent says
  something like "let me check" while it waits.
- If a request takes longer than *Tool Wait* (default 20 s), the agent is told it is
  still running and checks back with `check_assistant_result`.
- After the call, Open Assistant pulls the transcript from ElevenLabs and stores it in the
  voice conversation, so the assistant remembers what was only said to the voice model.
- If you hang up before a result is collected, it is sent to Slack (default channel) or
  WhatsApp (owner), depending on *Fallback Channel*.

The assistant's questions (`ask_user`) come back as `question`; when you answer, the
agent calls `ask_assistant` again and the run resumes.

!!! note "No phone calls"
    Phone numbers (Twilio) are handled entirely inside ElevenLabs, with no browser in the
    loop, so they can only reach the assistant through server tools, which means an
    internet-facing endpoint. This integration deliberately does not do that.

## Setup

1. **ElevenLabs** → Agents → create (or pick) an agent.
    - Choose a fast LLM and add guidance to the system prompt, for example:

      > You are a voice front-end for the user's personal assistant. Chat naturally and
      > briefly. When the user wants anything done or looked up, say a short filler
      > ("Let me check that"), then call `ask_assistant` with a complete, self-contained
      > request and read back the `answer`. If the status is `working`, tell the user you
      > are still on it and call `check_assistant_result` with the `job_id`. If a
      > `question` comes back, ask it and pass the reply to `ask_assistant`.
    - Add the two **client tools** from
      [`elevenlabs/agent-tools.json`](elevenlabs/agent-tools.json) (*Wait for response*
      on).
    - In the agent's security settings, keep it private (signed URLs only) and, if you
      like, restrict the allowed hosts to your instance's address.
2. **Open Assistant** → Settings → Integrations → *ElevenLabs Voice*:
    - Enable it, paste the **API Key** and the **Agent ID**, and use *Test connection*.
    - Optionally choose a **Fallback Channel**.
3. Open **Talk** in the navbar and tap the microphone.

## Microphone access needs a secure origin

Browsers only allow microphone access on `https://` pages or on `http://localhost`. If
you reach Open Assistant over plain `http://` on your LAN, the Talk page will say so. Use
`localhost`, or put it behind HTTPS. A private option that stays off the public internet is
[Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve) or a local reverse proxy
with a certificate.

## Security

- The API key is stored encrypted and used only for outbound requests to ElevenLabs.
- The `/api/elevenlabs/*` endpoints are same-origin web UI endpoints and are as protected
  as the rest of the UI (like `/api/chat`). Keep the instance reachable only by you.
- The Talk page loads no third-party scripts: the ElevenLabs client library and its audio
  worklet are served from `static/js` (see `static/js/VENDORED.md`). Voice audio goes from
  your browser straight to ElevenLabs.

## Limits

- Browser only: you must have the Talk page open for a conversation.
- Outbound calls and proactive voice notifications are not supported.
- Pending requests are held in memory in a single process (the default deployment).
