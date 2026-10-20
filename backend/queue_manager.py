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


async def add_forward_job(user_id: int, dest_chat, dest_topic, from_chat: int, message_id: int, lecture_id: str, title: str):
    """
    Enqueues a lecture forward job from the master forum group to the user's destination.
    If dest_chat is not set, defaults to user's private chat (PM) with the bot.
    """
    if not dest_chat or str(dest_chat).lower() in ("none", "null", "pm", "me", ""):
        dest_chat = user_id

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


async def process_job(client: TelegramClient, job: dict) -> bool:
    """
    Executes delivery of one lecture to the user's destination chat.
    Sends cleanly without 'Forwarded from' header whenever possible.
    Safely handles topic IDs (omits reply_to for Topic 1/General to prevent Telegram RPC errors).
    """
    user_id = job["user_id"]
    dest_chat = job["dest_chat"]
    dest_topic_raw = job.get("dest_topic")
    from_chat = job["from_chat"]
    message_id = job["message_id"]
    lecture_id = job["lecture_id"]
    title = job["title"]

    try:
        # 1. Resolve destination chat (defaults to user PM if unset)
        target_chat = dest_chat
        if not target_chat or str(target_chat).lower() in ("none", "null", "pm", "me", ""):
            target_chat = user_id
        elif isinstance(target_chat, str) and (target_chat.startswith("-100") or target_chat.lstrip("-").isdigit()):
            target_chat = int(target_chat)

        dest_entity = await client.get_entity(target_chat)

        source_peer = from_chat
        if isinstance(from_chat, str) and (from_chat.startswith("-100") or from_chat.lstrip("-").isdigit()):
            source_peer = int(from_chat)

        # 2. Normalize destination topic (Topic 1 is General thread, requires no reply_to)
        topic_reply = None
        if dest_topic_raw and str(dest_topic_raw).lower() not in ("none", "null", ""):
            try:
                t_int = int(dest_topic_raw)
                if t_int > 1:
                    topic_reply = t_int
            except (ValueError, TypeError):
                topic_reply = None

        # 3. Fetch original message to send clean copy without 'Forwarded from' tag
        delivered = False
        try:
            source_msg = await client.get_messages(source_peer, ids=message_id)
            if source_msg and source_msg.media:
                send_kwargs = {
                    "caption": source_msg.message or "",
                    "formatting_entities": getattr(source_msg, "entities", None)
                }
                if topic_reply:
                    send_kwargs["reply_to"] = topic_reply

                try:
                    await client.send_file(dest_entity, source_msg.media, **send_kwargs)
                    delivered = True
                except Exception as file_err:
                    # If failed with topic error, retry without topic into general/root
                    if topic_reply and ("TOPIC" in str(file_err).upper() or "REPLY" in str(file_err).upper()):
                        logger.warning(f"Topic reply {topic_reply} failed ({file_err}). Retrying into group root...")
                        send_kwargs.pop("reply_to", None)
                        await client.send_file(dest_entity, source_msg.media, **send_kwargs)
                        delivered = True
                    else:
                        raise file_err

            elif source_msg and source_msg.message:
                send_kwargs = {
                    "message": source_msg.message,
                    "formatting_entities": getattr(source_msg, "entities", None)
                }
                if topic_reply:
                    send_kwargs["reply_to"] = topic_reply
                await client.send_message(dest_entity, **send_kwargs)
                delivered = True

        except Exception as copy_err:
            logger.debug(f"Direct send_file copy notice: {copy_err}. Attempting forward_messages fallback...")

        # 4. Fallback to forward_messages if send_file could not be used
        if not delivered:
            fwd_kwargs = {
                "entity": dest_entity,
                "messages": message_id,
                "from_peer": source_peer
            }
            if topic_reply:
                fwd_kwargs["reply_to"] = topic_reply

            try:
                # Attempt forward with drop_author=True to strip forward tag
                await client.forward_messages(drop_author=True, **fwd_kwargs)
            except Exception:
                # Standard forward fallback
                if "drop_author" in fwd_kwargs:
                    fwd_kwargs.pop("drop_author", None)
                await client.forward_messages(**fwd_kwargs)

        record_chat_message_sent(str(dest_chat))
        logger.info(f"✅ Delivered: '{title}' -> {dest_chat} (Topic: {topic_reply or 'None/General'})")

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
