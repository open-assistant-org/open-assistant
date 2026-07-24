"""Shared concurrency primitives for blocking LLM calls and async sub-tasks.

Background
----------
Every LLM request in the app is a *blocking* HTTP call (the OpenAI SDK is
synchronous) that we offload with ``asyncio.to_thread``.  ``to_thread`` uses
the interpreter's **default** ``ThreadPoolExecutor`` whose size is only
``min(32, cpu_count + 4)`` — 8 threads on a 4-CPU box.  That pool is shared by
*everything* in the process.

When the async sub-task feature fans out several background research loops,
each loop holds a worker thread for the full duration of every LLM call.  A
handful of concurrent sub-tasks can therefore occupy the entire default pool,
and a freshly launched interactive chat has to queue for a free thread before
its first LLM call even starts — which is exactly why "the UI doesn't load
easily" while sub-tasks are running.

This module provides two things to decouple those workloads:

1. :func:`run_llm_blocking` — runs blocking LLM calls on a **dedicated**,
   generously sized pool that is separate from the default executor, so
   interactive requests and background work no longer compete for the same
   8 threads.
2. Sub-task fan-out limits — :func:`get_subtask_semaphore` bounds how many
   background sub-tasks run at once (reserving pool headroom for interactive
   chats), and the ``subtask_depth`` context variable bounds recursive
   fan-out so sub-tasks dispatching sub-tasks cannot exhaust the pool.
"""

import asyncio
import contextvars
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Dedicated LLM thread pool
# ---------------------------------------------------------------------------
# Sized well above the default min(32, cpu+4) so a burst of concurrent LLM
# calls (interactive request + several background sub-tasks) all get a worker
# thread immediately instead of queueing.  Override with LLM_THREAD_POOL_SIZE.
_LLM_POOL_SIZE = max(4, int(os.getenv("LLM_THREAD_POOL_SIZE", "32")))

_llm_executor = ThreadPoolExecutor(
    max_workers=_LLM_POOL_SIZE,
    thread_name_prefix="llm",
)

logger.info("LLM thread pool initialized with %d workers", _LLM_POOL_SIZE)


async def run_llm_blocking(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run a blocking LLM call on the dedicated LLM thread pool.

    Drop-in replacement for ``asyncio.to_thread(func, *args, **kwargs)`` that
    targets the dedicated pool instead of the shared default executor, keeping
    background sub-task traffic from starving interactive requests.
    """
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(_llm_executor, call)


# ---------------------------------------------------------------------------
# Sub-task fan-out limits
# ---------------------------------------------------------------------------
# Maximum number of dispatched sub-tasks allowed to run concurrently.  Kept
# below the LLM pool size so there are always free threads for the interactive
# request that spawned them.  Override with MAX_CONCURRENT_SUBTASKS.
MAX_CONCURRENT_SUBTASKS = max(1, int(os.getenv("MAX_CONCURRENT_SUBTASKS", "6")))

# Maximum recursion depth for sub-tasks dispatching further sub-tasks.
# Depth 0 is the top-level (coordinator) request; a value of 3 allows
# coordinator -> child -> grandchild fan-out but stops runaway recursion.
MAX_SUBTASK_DEPTH = max(1, int(os.getenv("MAX_SUBTASK_DEPTH", "3")))

# Tracks how deep in the sub-task tree the current execution is.  Because
# ``asyncio.create_task`` copies the current context, a sub-task launched from
# within another sub-task inherits the parent's depth automatically; the
# dispatcher resets it to the child's own depth inside the worker coroutine.
subtask_depth: contextvars.ContextVar[int] = contextvars.ContextVar("subtask_depth", default=0)

_subtask_semaphore: Optional[asyncio.Semaphore] = None


def get_subtask_semaphore() -> asyncio.Semaphore:
    """Return the process-wide sub-task concurrency semaphore.

    Created lazily so it binds to the running event loop the first time a
    sub-task is dispatched.
    """
    global _subtask_semaphore
    if _subtask_semaphore is None:
        _subtask_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUBTASKS)
    return _subtask_semaphore


def current_subtask_depth() -> int:
    """Return the sub-task depth of the current execution context."""
    return subtask_depth.get()
