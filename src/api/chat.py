"""Chat API with skills-based message handling."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.core.dependencies import get_message_handler, get_settings_service
from src.core.tools.definitions import initialize_all_tools
from src.models.conversation import ChatRequest, ChatResponse, PendingInput
from src.services.message_handler import MessageHandler
from src.services.settings import SettingsService
from src.utils.logger import get_logger
from src.utils.token_counter import count_tokens

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# Initialize tools at module level
initialize_all_tools()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    message_handler: MessageHandler = Depends(get_message_handler),
    settings_service: SettingsService = Depends(get_settings_service),
) -> ChatResponse:
    """Handle chat messages through the skills-based MessageHandler system."""
    try:
        # Verify LLM configuration
        api_key = settings_service.get_config_with_fallback("llm.api_key")
        if not api_key:
            logger.error("LLM API key not configured")
            raise HTTPException(
                status_code=500,
                detail="LLM API key not configured. Please configure it in Settings or set LLM_API_KEY environment variable.",
            )

        logger.info(
            f"Chat request: channel={request.channel}, "
            f"message_length={len(request.message)}, "
            f"conversation_id={request.conversation_id}"
        )

        # Get model for token counting
        model = settings_service.get_config_with_fallback(
            "llm.model", "anthropic/claude-3.5-sonnet"
        )

        # Handle message through MessageHandler
        result = await message_handler.handle_message(
            message=request.message,
            conversation_id=request.conversation_id,
            channel=request.channel,
            contact_identifier=request.contact_identifier,
            metadata={"source": "chat_api"},
        )

        # Calculate token usage (approximate)
        prompt_tokens = count_tokens(request.message, model)
        completion_tokens = count_tokens(result["response"], model)
        total_tokens = prompt_tokens + completion_tokens

        logger.info(
            f"Chat completed: conversation_id={result['conversation_id']}, "
            f"skills={result['skills_used']}, "
            f"tools={len(result['tools_executed'])}, "
            f"iterations={result['iterations']}, "
            f"tokens={total_tokens}"
        )

        # Build pending_input if the execution was suspended
        pending_input = None
        if result.get("pending_input"):
            pi = result["pending_input"]
            pending_input = PendingInput(
                question=pi["question"],
                options=pi.get("options"),
                context=pi.get("context"),
            )

        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            message_id=None,
            token_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            metadata={
                "skills_used": result["skills_used"],
                "tools_executed": result["tools_executed"],
                "iterations": result["iterations"],
                "stuck_detected": result["stuck_detected"],
            },
            pending_input=pending_input,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat request: {type(e).__name__}: {str(e)}",
        )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    message_handler: MessageHandler = Depends(get_message_handler),
    settings_service: SettingsService = Depends(get_settings_service),
) -> StreamingResponse:
    """Stream chat progress events via Server-Sent Events.

    Emits JSON-encoded SSE frames for each tool call and iteration, then a
    final ``complete`` (or ``error``) frame containing the full response.
    The browser reads this with fetch + ReadableStream so the user sees
    tool activity in real time without waiting for the full response.
    """
    api_key = settings_service.get_config_with_fallback("llm.api_key")
    if not api_key:
        # Return SSE error frame so the client can handle it uniformly
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'error': 'LLM API key not configured'})}\n\n"

        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    model = settings_service.get_config_with_fallback("llm.model", "anthropic/claude-3.5-sonnet")

    queue: asyncio.Queue = asyncio.Queue()

    async def event_callback(event: dict) -> None:
        await queue.put(event)

    async def run_handler() -> None:
        try:
            result = await message_handler.handle_message(
                message=request.message,
                conversation_id=request.conversation_id,
                channel=request.channel,
                contact_identifier=request.contact_identifier,
                metadata={"source": "chat_api_stream"},
                event_callback=event_callback,
            )
            prompt_tokens = count_tokens(request.message, model)
            completion_tokens = count_tokens(result["response"], model)
            pending_input = None
            if result.get("pending_input"):
                pi = result["pending_input"]
                pending_input = {
                    "question": pi["question"],
                    "options": pi.get("options"),
                    "context": pi.get("context"),
                }
            await queue.put(
                {
                    "type": "complete",
                    "response": result["response"],
                    "conversation_id": result["conversation_id"],
                    "metadata": {
                        "skills_used": result["skills_used"],
                        "tools_executed": result["tools_executed"],
                        "iterations": result["iterations"],
                        "stuck_detected": result["stuck_detected"],
                    },
                    "token_usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                    "pending_input": pending_input,
                }
            )
        except Exception as e:
            logger.error(f"Error in chat stream: {type(e).__name__}: {str(e)}", exc_info=True)
            await queue.put({"type": "error", "error": f"{type(e).__name__}: {str(e)}"})

    # Padding comment that exceeds nginx's default proxy_busy_buffers_size (8 KB),
    # forcing an immediate buffer flush on every frame without proxy config changes.
    _FLUSH_PAD = ": " + " " * 8192 + "\n"

    async def sse_generator():
        handler_task = asyncio.create_task(run_handler())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield f": keepalive{' ' * 8186}\n\n"
                    continue
                yield f"{_FLUSH_PAD}data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
        finally:
            handler_task.cancel()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
