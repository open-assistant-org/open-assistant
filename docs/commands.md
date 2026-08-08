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

---

## `/cancel`

Stop all ongoing work in the current conversation and return to a clean state — without leaving the thread.

```
/cancel
```

**Response**: `⛔ All ongoing work has been stopped. You can start a new request whenever you're ready.`  
(If background tasks were running, the response also lists how many were cancelled and their IDs.)

### Why use it

Open Assistant can run long multi-step plans and dispatch parallel background tasks on your behalf. Most of the time this is exactly what you want — but occasionally the model gets stuck in a loop, pursues the wrong approach, or you simply change your mind mid-flight.

- **Loop detected too late.** The built-in stuck-detection kicks in automatically, but it takes a few repeated iterations to trigger. `/cancel` lets you cut it short the moment you notice something is off.
- **Wrong plan, wrong direction.** If the model misunderstood the request and is off on a long tangent, waiting for it to finish wastes time and tokens.
- **Background tasks you no longer need.** `dispatch_task` spawns sub-tasks that run concurrently. `/cancel` stops all of them for the current conversation immediately.
- **Suspended `ask_user` prompts.** If the model paused mid-plan to ask you a question but you want to start fresh instead of answering, `/cancel` clears that suspended state.

### When to use it

Use `/cancel` when:

- The assistant appears stuck — repeating the same tool calls or making no visible progress.
- You realise mid-response that you phrased the request wrong and want to try again.
- A multi-step plan is running but you want to change course before it finishes.
- You see background tasks spinning (the tool-call indicator keeps appearing) and want them stopped.

### Difference from `/clear`

| | `/cancel` | `/clear` |
|---|---|---|
| Stops ongoing work | ✅ Yes | ✅ Only because a new conversation is started |
| Stays in the same thread | ✅ Yes | ❌ No — starts a new conversation |
| Preserves conversation history | ✅ Yes | ✅ Yes (old thread is kept, a new one begins) |
| Use when… | You want to interrupt and retry **in the same thread** | You are switching to a **different topic** entirely |

### What happens under the hood

When you type `/cancel`:

1. Every running background sub-task for the active conversation has its asyncio future cancelled and is marked `"cancelled"` in the task store.
2. Any suspended `ask_user` execution state is cleared, so the next message you send is treated as a fresh request rather than an answer to a previous question.
3. Both the `/cancel` command and the assistant's acknowledgement are stored in the conversation history, keeping the thread coherent.
4. The response is returned immediately — no LLM call is made.
