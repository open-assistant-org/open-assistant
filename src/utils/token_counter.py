"""Token counting utility for different LLM models."""

from typing import List, Optional

import tiktoken

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Model to encoding mapping
MODEL_ENCODINGS = {
    # Default
    "default": "cl100k_base",
}


def get_encoding_for_model(model: str) -> str:
    """
    Get the tiktoken encoding name for a model.

    Args:
        model: Model name or identifier

    Returns:
        Encoding name (e.g., "cl100k_base")
    """
    # Extract base model name (handle provider prefixes like "anthropic/")
    base_model = model.split("/")[-1] if "/" in model else model

    # Check exact match
    if base_model in MODEL_ENCODINGS:
        return MODEL_ENCODINGS[base_model]

    # Check partial match
    for model_key, encoding in MODEL_ENCODINGS.items():
        if model_key in base_model:
            return encoding

    # Default
    logger.warning(f"Unknown model '{model}', using default encoding")
    return MODEL_ENCODINGS["default"]


def count_tokens(text: str, model: str = "default") -> int:
    """
    Count tokens in text for a specific model.

    Args:
        text: Text to count tokens for
        model: Model name (e.g., "gpt-4", "claude-3.5-sonnet")

    Returns:
        Number of tokens

    Example:
        >>> count_tokens("Hello, world!", "gpt-4")
        4
    """
    try:
        encoding_name = get_encoding_for_model(model)
        encoding = tiktoken.get_encoding(encoding_name)
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        # Fallback: rough approximation (4 chars per token)
        return len(text) // 4


def count_message_tokens(messages: List[dict], model: str = "default") -> int:
    """
    Count tokens for a list of messages (chat format).

    Args:
        messages: List of message dictionaries with 'role' and 'content'
        model: Model name

    Returns:
        Total token count including message formatting overhead

    Note:
        This includes approximate overhead for message formatting
        (role labels, separators, etc.)
    """
    try:
        encoding_name = get_encoding_for_model(model)
        encoding = tiktoken.get_encoding(encoding_name)

        total_tokens = 0

        # Message formatting overhead (approximate)
        # Each message has role + content + separators
        tokens_per_message = 4  # Overhead per message
        tokens_per_name = 1  # If name field is present

        for message in messages:
            total_tokens += tokens_per_message

            # Count role
            if "role" in message:
                total_tokens += len(encoding.encode(message["role"]))

            # Count content
            if "content" in message:
                total_tokens += len(encoding.encode(message["content"]))

            # Count name if present
            if "name" in message:
                total_tokens += tokens_per_name
                total_tokens += len(encoding.encode(message["name"]))

        # Add final overhead
        total_tokens += 3  # Every reply is primed with assistant

        return total_tokens

    except Exception as e:
        logger.error(f"Error counting message tokens: {e}")
        # Fallback: sum content lengths / 4
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """
    Estimate API cost based on token counts.

    Args:
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        model: Model name

    Returns:
        Estimated cost in USD

    Note:
        Prices are approximate and may change. Update regularly.
    """
    # Pricing per 1M tokens (as of 2024-01)
    # Format: (input_cost_per_1M, output_cost_per_1M)
    pricing = {}

    # Extract base model name
    base_model = model.split("/")[-1] if "/" in model else model

    # Find pricing
    input_cost_per_1m, output_cost_per_1m = pricing.get(base_model, (5.0, 15.0))  # Default estimate

    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * output_cost_per_1m

    return input_cost + output_cost


def truncate_to_token_limit(text: str, max_tokens: int, model: str = "default") -> str:
    """
    Truncate text to fit within token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        model: Model name

    Returns:
        Truncated text that fits within token limit
    """
    try:
        encoding_name = get_encoding_for_model(model)
        encoding = tiktoken.get_encoding(encoding_name)

        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        # Truncate tokens
        truncated_tokens = tokens[:max_tokens]

        # Decode back to text
        truncated_text = encoding.decode(truncated_tokens)

        logger.debug(f"Truncated text from {len(tokens)} to {max_tokens} tokens")

        return truncated_text

    except Exception as e:
        logger.error(f"Error truncating text: {e}")
        # Fallback: character-based truncation
        approx_chars = max_tokens * 4
        return text[:approx_chars]
