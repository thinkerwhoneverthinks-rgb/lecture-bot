import asyncio
import time
import logging
from collections import defaultdict
from telethon import TelegramClient, errors
from config import (
    ALL_BOT_TOKENS,
    QUEUE_DISPATCH_INTERVAL,
    QUEUE_BUSY_THRESHOLD,
    RATE_LIMIT_PER_CHAT_MAX_RPM,
    logger
)
from user_storage import save_user_data, get_or_create_user_data

# Global Asyncio Queue
JOB_QUEUE = asyncio.Queue()

# Per-chat rate limit tracker (timestamp history to enforce max 20 msg/min to SAME chat)
CHAT_HISTORY = defaultdict(list)

# Clients pool for multi-token round-robin
CLIENT_POOL = []
current_worker_index = 0


def get_queue_status() -> dict:
    """
    Returns queue status without exposing raw position numbers to students.
    If qsize > QUEUE_BUSY_THRESHOLD, triggers student-friendly busy mode.
    """
    size = JOB_QUEUE.qsize()
    return {
        "is_busy": size > QUEUE_BUSY_THRESHOLD,
        "backlog_count": size,
        "worker_count": len(CLIENT_POOL) if CLIENT_POOL else 1
    }


def is_chat_rate_limited(dest_chat: str) -> bool:
    """Enforces Telegram's 20 messages per minute rule to the same chat."""
    now = time.time()
    one_min_ago = now - 60.0
    history = [t for t in CHAT_HISTORY[dest_chat] if t > one_min_ago]
    CHAT_HISTORY[dest_chat] = history
    return len(history) >= RATE_LIMIT_PER_CHAT_MAX_RPM


def record_chat_message_sent(dest_chat: str):
    """Records a timestamp when a message is successfully delivered to a chat."""
    CHAT_HISTORY[dest_chat].append(time.time())


async def add_forward_job(user_id: int, dest_chat: str, dest_topic, from_chat: int, message_id: int, lecture_id: str, title: str):
    """
    Enqueues a lecture forward job from the master forum group to the user's destination.
    """
    job = {
        "user_id": user_id,
        "dest_chat": dest_chat,
        "dest_topic": dest_topic,
        "from_chat": from_chat,
        "message_id": message_id,
        "lecture_id": lecture_id,
        "title": title,
        "retries": 0,
        "enqueued_at": time.time()
    }
    await JOB_QUEUE.put(job)
    logger.info(f"📥 Enqueued job: '{title}' for user {user_id} -> {dest_chat} (Queue size: {JOB_QUEUE.qsize()})")
    return job


async def start_queue_workers(clients: list):
    """
    Spawns background dispatcher that processes jobs with 0.05s delay,
    round-robin rotates across worker bot tokens, and gracefully handles 429 FloodWait.
    """
    global CLIENT_POOL, current_worker_index
    CLIENT_POOL = clients

    if not CLIENT_POOL:
        logger.error("No Telegram clients available in pool for queue worker!")
        return

    logger.info(f"🚀 Queue worker started with {len(CLIENT_POOL)} bot client(s) in pool.")

    while True:
        try:
            job = await JOB_QUEUE.get()

            # Check per-chat rate limiting to avoid 429 FloodWait on same chat
            dest_chat = str(job["dest_chat"])
            if is_chat_rate_limited(dest_chat):
                logger.warning(f"⏳ Chat {dest_chat} hit 20 msg/min threshold. Delaying job for 3s...")
                await asyncio.sleep(3.0)
                await JOB_QUEUE.put(job)
                JOB_QUEUE.task_done()
                continue

            # Pick next client via Round-Robin
            client = CLIENT_POOL[current_worker_index % len(CLIENT_POOL)]
            current_worker_index += 1

            # Dispatch forward
            success = await process_job(client, job)
            if not success and job["retries"] < 3:
                job["retries"] += 1
                logger.info(f"🔁 Re-queuing job '{job['title']}' (retry {job['retries']}/3)")
                await JOB_QUEUE.put(job)

            JOB_QUEUE.task_done()
            # 50ms delay between dispatches
            await asyncio.sleep(QUEUE_DISPATCH_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Unexpected error in queue worker: {e}", exc_info=True)
            await asyncio.sleep(1.0)


async def process_job(client: TelegramClient, job: dict) -> bool:
    """Executes forwarding of one lecture to the user's destination chat."""
    user_id = job["user_id"]
    dest_chat = job["dest_chat"]
    dest_topic = job["dest_topic"]
    from_chat = job["from_chat"]
    message_id = job["message_id"]
    lecture_id = job["lecture_id"]
    title = job["title"]
    try:
        # Resolve destination
        target_chat = dest_chat
        if isinstance(dest_chat, str) and (dest_chat.startswith("-100") or dest_chat.lstrip("-").isdigit()):
            target_chat = int(dest_chat)
        dest_entity = await client.get_entity(target_chat)

        source_peer = from_chat
        if isinstance(from_chat, str) and (from_chat.startswith("-100") or from_chat.lstrip("-").isdigit()):
            source_peer = int(from_chat)

        # Forward or Copy message
        forward_kwargs = {
            "entity": dest_entity,
            "messages": message_id,
            "from_peer": source_peer
        }
        if dest_topic:
            forward_kwargs["reply_to"] = int(dest_topic)

        await client.forward_messages(**forward_kwargs)
        record_chat_message_sent(str(dest_chat))

        logger.info(f"✅ Delivered: '{title}' -> {dest_chat}")

        # Update user's sent_lectures in pinned DB
        u_data = await get_or_create_user_data(client, user_id)
        if lecture_id not in u_data.get("sent_lectures", []):
            u_data.setdefault("sent_lectures", []).append(lecture_id)
            await save_user_data(client, user_id, u_data)

        return True

    except errors.FloodWaitError as e:
        logger.warning(f"⚠️ Telegram 429 FloodWait: Must sleep for {e.seconds} seconds.")
        await asyncio.sleep(e.seconds + 1)
        return False

    except errors.ChatAdminRequiredError:
        logger.error(f"❌ Bot is not admin in destination chat {dest_chat} for user {user_id}!")
        return False

    except errors.UserBannedInChannelError:
        logger.error(f"❌ Bot is banned or cannot write in destination chat {dest_chat}!")
        return False

    except Exception as e:
        logger.error(f"Failed to forward message {message_id} to {dest_chat}: {e}")
        return False
