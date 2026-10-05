# ElevenLabs Voice Agent

Talk to your assistant by voice (web widget or phone) through an
[ElevenLabs](https://elevenlabs.io) conversational agent. It behaves like another
channel next to Slack and WhatsApp: voice requests run through the same skills,
tools and memory, under the channel name `elevenlabs`.

## How it works

```
caller ──voice──▶ ElevenLabs agent (fast LLM: small talk, clarifications)
                      │  server tool: ask_assistant
                      ▼
              Open Assistant  /api/elevenlabs/tools/ask_assistant
                      │  MessageHandler.handle_message(channel="elevenlabs")
                      ▼
              answer (speech-friendly text) ──▶ spoken to the caller
```

The assistant itself is not fast enough to answer every voice turn (a plain answer
takes a few seconds, tool use longer), so the **voice LLM stays inside ElevenLabs**
and only calls the assistant when real work is needed, saying "let me check" while
it waits.

- **`ask_assistant`** runs the request. If it finishes within *Tool Wait*
  (default 20 s) the answer comes back; otherwise it returns `status: "working"`
  with a `job_id`.
- **`check_assistant_result`** collects a job that was still running.
- **Post-call webhook** stores the full transcript as a message in the voice
  conversation, so the assistant also remembers what was only said to the voice
  model.
- **Fallback channel**: if the caller hangs up before a result is collected, it is
  sent to Slack (default channel) or WhatsApp (owner), if configured.

The assistant's questions (`ask_user`) come back as `question`; when the caller
answers, the voice agent calls `ask_assistant` again and the run resumes.

!!! note
    Pending jobs live in memory in a single process (the default deployment).

## Setup

1. **Open Assistant** → Settings → Integrations → *ElevenLabs Voice*:
    - Enable it and set **Tool Secret** to a long random string
      (`openssl rand -hex 32`).
    - Optionally set **Fallback Channel**.
2. **ElevenLabs** → Agents → your agent:
    - Add a workspace secret `open_assistant_tool_secret` with the same value.
    - Create the two server tools from [`elevenlabs/agent-tools.json`](elevenlabs/agent-tools.json)
      (replace `YOUR_APP_URL`; your instance must be reachable over HTTPS from the
      internet, `APP_URL`).
    - Pick a fast LLM and add guidance to the system prompt, for example:

      > You are a voice front-end for the user's personal assistant. Chat naturally
      > and briefly. When the user wants anything done or looked up, say a short
      > filler ("Let me check that"), then call `ask_assistant` with a complete,
      > self-contained request, and read back the `answer`. If the status is
      > `working`, tell the user you're still on it and call `check_assistant_result`
      > with the `job_id`. If a `question` is returned, ask it and pass the reply
      > to `ask_assistant`.
3. **Post-call webhook** (ElevenLabs → Settings → Webhooks): create a webhook to
   `https://YOUR_APP_URL/api/elevenlabs/webhooks/post-call` for *transcription*
   events, and copy its secret into **Post-call Webhook Secret**.
4. Optional: import a Twilio number into the agent for phone calls.

Set the ElevenLabs tool response timeout a few seconds above *Tool Wait*.

## Security

- Tool calls require `Authorization: Bearer <Tool Secret>`; webhooks require a valid
  `ElevenLabs-Signature` (HMAC-SHA256, 30 minute tolerance). Without a configured
  secret, the endpoints reject every request.
- Anyone holding the Tool Secret can make the assistant act as you. Treat it like a
  password and rotate it if it leaks.

## Limits

- Voice requests are answered by the assistant, not the voice LLM, so latency is
  that of a normal chat turn.
- Outbound calls and proactive voice notifications are not supported.
