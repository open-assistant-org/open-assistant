# Commands

Open Assistant supports a small set of slash commands you can type directly in any conversation.

## `/clear`

Start a fresh conversation thread.

```
/clear
```

**Response**: `Conversation cleared.`

### Why use it

Open Assistant keeps the full message history of the current conversation in context when forming its responses. This is great for continuity within a single topic, but it becomes a liability once the conversation drifts:

- **Mixed topics confuse the model.** If you ask about your calendar, then pivot to drafting an email, then ask something unrelated, the model has to reason over a noisy, multi-topic thread. Responses become less focused and more likely to carry over irrelevant context.
- **Long threads cost more tokens.** Every message in the active thread is sent to the LLM. A sprawling thread inflates cost and latency with no benefit once the earlier topic is closed.
- **Cross-conversation context is already handled.** You do not lose history by clearing. `memory_recall` (the assistant's persistent memory store) and conversation search give it access to past conversations when genuinely relevant. The old thread stays intact and searchable — `/clear` only starts a new one for the next topic.

### When to use it

Use `/clear` when:

- You are switching to a clearly different topic (e.g. you were planning a trip, now you want to manage emails).
- The conversation has grown long and responses feel less sharp or are mixing up context from earlier messages.
- You notice the assistant referencing something from earlier in the thread that is no longer relevant.

A good rule of thumb: one thread, one topic. When the topic changes, `/clear`.

### What happens under the hood

`/clear` creates a brand-new conversation with a fresh ID and routes all subsequent messages to it. The previous conversation is **not deleted** — it remains fully available in your conversation history and can be searched or referenced by the assistant's memory tools.
