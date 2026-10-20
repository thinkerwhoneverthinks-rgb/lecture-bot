import os
import json
import re
import asyncio
from aiohttp import web
from telethon import TelegramClient, events, Button

from config import (
    API_ID,
    API_HASH,
    MAIN_BOT_TOKEN,
    WORKER_BOT_TOKENS,
    ALL_BOT_TOKENS,
    FORUM_CHAT_ID,
    ADMIN_ID,
    HOST,
    PORT,
    WEBAPP_URL,
    FORCE_SUB_CHANNEL,
    FORCE_SUB_INVITE_LINK,
    logger
)
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import UserNotParticipantError
from telethon import errors
from scanner import (
    scan_master_forum,
    get_lecture_map,
    load_catalog_config,
    toggle_hidden_topic,
    add_curated_chapter
)
from user_storage import (
    get_or_create_user_data,
    save_user_data,
    get_all_registered_users,
    sync_users_from_backup_channel
)
from queue_manager import (
    add_forward_job,
    start_queue_workers,
    get_queue_status
)

all_clients = []
main_client = None


async def check_user_subscribed(client: TelegramClient, user_id: int) -> bool:
    """
    Checks if a user is a member of the required FORCE_SUB_CHANNEL.
    If no channel is configured, returns True.
    """
    if not FORCE_SUB_CHANNEL or not client:
        return True

    try:
        channel_entity = await client.get_entity(FORCE_SUB_CHANNEL)
        await client(GetParticipantRequest(channel=channel_entity, participant=user_id))
        return True
    except UserNotParticipantError:
        return False
    except Exception as e:
        logger.warning(f"Could not verify channel subscription for {user_id}: {e}")
        # Fail-open if bot lacks rights or channel temp issue
        return True



# =================================================================
# AIOHTTP REST API HANDLERS (CALLED BY TELEGRAM MINI APP)
# =================================================================

async def handle_cors(request):
    """Adds standard CORS headers to permit Mini App requests."""
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )


async def api_get_lectures(request):
    """Returns the cached master LECTURE_MAP JSON for the Mini App."""
    return web.json_response(get_lecture_map(), headers={"Access-Control-Allow-Origin": "*"})


async def api_get_user_data(request):
    """
    Returns the user's progress and settings from their pinned DB message.
    Auto-restores from backup channel if user deleted their pinned message.
    """
    user_id_raw = request.query.get("user_id")
    if not user_id_raw:
        return web.json_response({"error": "Missing user_id parameter"}, status=400)

    user_id = int(user_id_raw)
    data = await get_or_create_user_data(main_client, user_id)
    return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})


def parse_telegram_destination(raw_input: str):
    """
    Parses any Telegram link or identifier:
    - https://t.me/wifu_free_leech_group/438727 -> ('@wifu_free_leech_group', None)
    - https://t.me/bhyffiyg/2 -> ('@bhyffiyg', None)
    - https://t.me/bhyffiyg/3/4 -> ('@bhyffiyg', 3)
    - https://t.me/c/4437369298/7 -> (-1004437369298, None)
    - https://t.me/c/4385985766/1/10 -> (-1004385985766, 1)
    - @username -> ('@username', None)
    - -100123456789 -> (-100123456789, None)
    - Empty / None / 'pm' / 'me' -> (None, None)
    """
    if not raw_input:
        return None, None
    s = str(raw_input).strip()
    if not s or s.lower() in ("none", "null", "pm", "me", "direct"):
        return None, None

    # Strip URL query parameters or hash if any (e.g. ?comment=123)
    s = s.split("?")[0].split("#")[0].strip()

    # Pattern 1: Private channel/group with topic: t.me/c/<channel_id>/<topic_id>/<msg_id>
    m = re.search(r"t\.me\/c\/(\d+)\/(\d+)\/(\d+)", s)
    if m:
        cid_str = m.group(1)
        channel_id = int(f"-{cid_str}") if (cid_str.startswith("100") and len(cid_str) > 12) else int(f"-100{cid_str}")
        topic_id = int(m.group(2))
        return channel_id, topic_id

    # Pattern 2: Private channel/group message or topic: t.me/c/<channel_id>/<msg_id_or_topic>
    m = re.search(r"t\.me\/c\/(\d+)\/(\d+)", s)
    if m:
        cid_str = m.group(1)
        channel_id = int(f"-{cid_str}") if (cid_str.startswith("100") and len(cid_str) > 12) else int(f"-100{cid_str}")
        return channel_id, None

    # Pattern 3: Private channel base link: t.me/c/<channel_id>
    m = re.search(r"t\.me\/c\/(\d+)", s)
    if m:
        cid_str = m.group(1)
        channel_id = int(f"-{cid_str}") if (cid_str.startswith("100") and len(cid_str) > 12) else int(f"-100{cid_str}")
        return channel_id, None

    # Pattern 4: Public group with topic: t.me/<username>/<topic_id>/<msg_id>
    m = re.search(r"t\.me\/([a-zA-Z0-9_]{4,})\/(\d+)\/(\d+)", s)
    if m:
        username = f"@{m.group(1)}"
        topic_id = int(m.group(2))
        return username, topic_id

    # Pattern 5: Public channel/group message: t.me/<username>/<msg_id>
    m = re.search(r"t\.me\/([a-zA-Z0-9_]{4,})\/(\d+)", s)
    if m:
        username = f"@{m.group(1)}"
        return username, None

    # Pattern 6: Public link base: t.me/<username>
    m = re.search(r"t\.me\/([a-zA-Z0-9_]{4,})", s)
    if m:
        username = f"@{m.group(1)}"
        return username, None

    # Pattern 7: Raw numeric chat id (-100... or ...)
    if s.startswith("-100") or s.lstrip("-").isdigit():
        try:
            return int(s), None
        except ValueError:
            return s, None

    # Pattern 8: @username
    if s.startswith("@"):
        return s, None

    return s, None


async def api_verify_destination(request):
    """
    Diagnostic endpoint that tests whether:
    1. The target chat exists and bot has access to it.
    2. The bot is an Administrator in the target chat with message posting rights.
    3. The topic (if specified) is valid.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"valid": False, "error": "Invalid request body"}, status=400)

    user_id = body.get("user_id")
    # Accept both destination_input, destination, and custom_group from client
    raw_input = body.get("destination_input") or body.get("destination") or body.get("custom_group")
    manual_topic = body.get("topic_id") or body.get("custom_topic")

    # If empty or explicit PM keywords, destination is user PM
    if not raw_input or str(raw_input).strip().lower() in ("", "none", "null", "pm", "me", "direct"):
        return web.json_response({
            "valid": True,
            "is_pm": True,
            "chat_title": "Bot Private Chat (PM)",
            "chat_id": str(user_id) if user_id else "PM",
            "topic_id": None,
            "message": "✅ Destination: Your Private Chat with Bot (PM). No admin rights required!"
        }, headers={"Access-Control-Allow-Origin": "*"})

    parsed_chat, parsed_topic = parse_telegram_destination(raw_input)
    final_chat = parsed_chat if parsed_chat is not None else raw_input

    # Priority for topic: explicit manual_topic if provided by user, else auto-parsed topic from URL
    final_topic = None
    if manual_topic is not None and str(manual_topic).strip().isdigit():
        final_topic = int(str(manual_topic).strip())
    elif parsed_topic is not None:
        final_topic = parsed_topic

    if not main_client:
        return web.json_response({"valid": False, "error": "Bot client not initialized"}, status=503)

    try:
        target_chat = final_chat
        if isinstance(target_chat, str) and (target_chat.startswith("-100") or target_chat.lstrip("-").isdigit()):
            try:
                target_chat = int(target_chat)
            except ValueError:
                pass

        # Fetch entity with fallback to get_dialogs cache refresh
        try:
            entity = await main_client.get_entity(target_chat)
        except Exception as e_first:
            logger.warning(f"First get_entity attempt failed for {target_chat}: {e_first}. Refreshing dialogs cache...")
            try:
                await main_client.get_dialogs(limit=100)
                entity = await main_client.get_entity(target_chat)
            except Exception:
                raise e_first

        chat_title = getattr(entity, 'title', None) or getattr(entity, 'username', None) or str(final_chat)

        # Check bot permissions in target channel/group
        is_admin = False
        can_post = False
        try:
            perms = await main_client.get_permissions(entity, 'me')
            is_admin = getattr(perms, 'is_admin', False) or getattr(perms, 'is_creator', False)
            can_post = getattr(perms, 'post_messages', False) or getattr(perms, 'send_messages', False) or is_admin
        except Exception as pe:
            logger.debug(f"Permissions probe note: {pe}")
            admin_rights = getattr(entity, 'admin_rights', None)
            if admin_rights:
                is_admin = True
                can_post = bool(getattr(admin_rights, 'post_messages', False) or getattr(admin_rights, 'send_messages', False))

        if not is_admin and not can_post:
            return web.json_response({
                "valid": False,
                "chat_title": chat_title,
                "chat_id": str(final_chat),
                "topic_id": final_topic,
                "error": f"⚠️ Bot is in '{chat_title}', but is NOT an Admin! Please promote the bot to Admin with 'Send Messages' rights."
            }, headers={"Access-Control-Allow-Origin": "*"})

        topic_note = f" (Topic ID: {final_topic})" if final_topic else ""
        return web.json_response({
            "valid": True,
            "is_pm": False,
            "chat_title": chat_title,
            "chat_id": str(final_chat),
            "topic_id": final_topic,
            "is_admin": is_admin,
            "message": f"✅ Verified! Bot is Admin in '{chat_title}'{topic_note}."
        }, headers={"Access-Control-Allow-Origin": "*"})

    except Exception as e:
        err_msg = str(e)
        logger.error(f"api_verify_destination error for {raw_input}: {err_msg}", exc_info=True)
        if "Cannot find any entity" in err_msg or "Could not find the input entity" in err_msg:
            return web.json_response({
                "valid": False,
                "error": "❌ Bot cannot access this channel/group! Make sure you: 1. Added the bot as Admin to the channel. 2. Sent a message in the channel."
            }, headers={"Access-Control-Allow-Origin": "*"})
        return web.json_response({
            "valid": False,
            "error": f"❌ Verification failed: {err_msg}"
        }, headers={"Access-Control-Allow-Origin": "*"})


async def api_save_settings(request):
    """
    Updates the user's destination group, topic ID, and optional custom bot token.
    Supports direct Telegram message links, chat IDs, or null for Bot PM delivery.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    raw_group = body.get("custom_group") or body.get("destination") or body.get("destination_input")
    raw_topic = body.get("custom_topic") or body.get("topic_id")
    custom_bot_token = body.get("custom_bot_token")

    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)

    user_id = int(user_id)
    data = await get_or_create_user_data(main_client, user_id)

    # Parse link if user provided a Telegram message link in custom_group
    parsed_chat, parsed_topic = parse_telegram_destination(raw_group)
    if parsed_chat is not None:
        data["custom_group"] = str(parsed_chat)
    elif raw_group and str(raw_group).strip().lower() not in ("none", "null", "pm", "me", ""):
        data["custom_group"] = str(raw_group).strip()
    else:
        data["custom_group"] = None

    if raw_topic is not None and str(raw_topic).strip() != "" and str(raw_topic).strip().isdigit():
        data["custom_topic"] = int(str(raw_topic).strip())
    elif parsed_topic is not None:
        data["custom_topic"] = parsed_topic
    else:
        data["custom_topic"] = None

    data["custom_bot_token"] = custom_bot_token

    # Resolve friendly title if destination is set and main_client is connected
    chat_title = None
    if data.get("custom_group") and main_client:
        try:
            target_chat = data["custom_group"]
            if str(target_chat).startswith("-100") or str(target_chat).lstrip("-").isdigit():
                target_chat = int(target_chat)
            entity = await main_client.get_entity(target_chat)
            chat_title = getattr(entity, 'title', None) or getattr(entity, 'username', None)
        except Exception:
            pass

    data["custom_group_title"] = chat_title

    saved = await save_user_data(main_client, user_id, data)
    return web.json_response({"success": saved, "data": data}, headers={"Access-Control-Allow-Origin": "*"})


async def api_queue_one(request):
    """
    Enqueues a single lecture forward task from Master Forum to User's Destination Group.
    If no destination is configured, gracefully defaults to the user's Bot PM chat.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    lecture_id = body.get("lecture_id")
    message_id = body.get("message_id")
    title = body.get("title", "Lecture")

    if not user_id or not message_id or not lecture_id:
        return web.json_response({"error": "Missing required fields"}, status=400)

    user_id = int(user_id)

    # Enforce Force Subscribe (FSUB)
    if not await check_user_subscribed(main_client, user_id):
        join_url = FORCE_SUB_INVITE_LINK or (f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}" if FORCE_SUB_CHANNEL else "")
        return web.json_response({
            "error": "🔒 You must join our official channel to forward lectures!",
            "fsub_required": True,
            "channel_url": join_url
        }, status=403, headers={"Access-Control-Allow-Origin": "*"})

    u_data = await get_or_create_user_data(main_client, user_id)

    dest_chat = u_data.get("custom_group")
    dest_topic = u_data.get("custom_topic")

    # If no destination group set, default directly to user's PM
    if not dest_chat or str(dest_chat).lower() in ("none", "null", "pm", "me", ""):
        dest_chat = user_id

    from_chat = body.get("from_chat") or FORUM_CHAT_ID
    if isinstance(from_chat, str) and (from_chat.startswith("-100") or from_chat.lstrip("-").isdigit()):
        from_chat = int(from_chat)

    # Put job in queue
    job = await add_forward_job(
        user_id=user_id,
        dest_chat=dest_chat,
        dest_topic=dest_topic,
        from_chat=from_chat,
        message_id=int(message_id),
        lecture_id=str(lecture_id),
        title=title
    )

    return web.json_response({
        "success": True,
        "queued": True,
        "title": title
    }, headers={"Access-Control-Allow-Origin": "*"})


async def api_check_fsub(request):
    """Checks if a user is subscribed to the required Force Subscribe channel."""
    user_id_raw = request.query.get("user_id")
    if not user_id_raw:
        return web.json_response({"error": "Missing user_id"}, status=400)
    user_id = int(user_id_raw)
    is_sub = await check_user_subscribed(main_client, user_id)
    join_url = FORCE_SUB_INVITE_LINK or (f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}" if FORCE_SUB_CHANNEL else "")
    return web.json_response({
        "required": bool(FORCE_SUB_CHANNEL),
        "is_subscribed": is_sub,
        "channel_url": join_url,
        "channel_name": FORCE_SUB_CHANNEL
    }, headers={"Access-Control-Allow-Origin": "*"})



async def api_complete_batch(request):
    """Saves a batch identifier to the user's completed_batches in their pinned DB."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    batch_key = body.get("batch_key")

    if not user_id or not batch_key:
        return web.json_response({"error": "Missing user_id or batch_key"}, status=400)

    user_id = int(user_id)
    data = await get_or_create_user_data(main_client, user_id)

    completed = data.setdefault("completed_batches", [])
    if batch_key not in completed:
        completed.append(batch_key)
        await save_user_data(main_client, user_id, data)

    return web.json_response({"success": True, "completed_batches": completed}, headers={"Access-Control-Allow-Origin": "*"})


async def api_queue_status(request):
    """Returns queue status (is_busy, worker_count, etc.) without exposing internal counts."""
    status = get_queue_status()
    return web.json_response(status, headers={"Access-Control-Allow-Origin": "*"})


# =================================================================
# ADMIN REST API HANDLERS (Authenticated via ADMIN_ID)
# =================================================================

def is_request_admin(user_id) -> bool:
    if not ADMIN_ID or not user_id:
        return False
    try:
        return int(user_id) == int(ADMIN_ID)
    except (ValueError, TypeError):
        return False


async def api_admin_info(request):
    """Returns comprehensive system metrics, topic list, and curation config for Admin."""
    user_id = request.query.get("user_id")
    if not is_request_admin(user_id):
        return web.json_response({"error": "Unauthorized", "is_admin": False}, status=403, headers={"Access-Control-Allow-Origin": "*"})

    config = load_catalog_config()
    users = get_all_registered_users()
    q = get_queue_status()

    catalog = get_lecture_map()
    return web.json_response({
        "is_admin": True,
        "admin_id": ADMIN_ID,
        "total_students": len(users),
        "total_lectures": catalog.get("total_lectures", 0),
        "topics": catalog.get("all_topics", catalog.get("topics", [])),
        "hidden_topics": [str(h) for h in config.get("hidden_topics", [])],
        "categories": config.get("categories", []),
        "last_scanned": catalog.get("last_scanned"),
        "queue": q
    }, headers={"Access-Control-Allow-Origin": "*"})


async def api_admin_toggle_topic(request):
    """Toggles topic visibility (hide/show) in catalog_config.json and updates catalog."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    topic_key = body.get("topic_key")
    if not is_request_admin(user_id):
        return web.json_response({"error": "Unauthorized"}, status=403, headers={"Access-Control-Allow-Origin": "*"})

    if not topic_key:
        return web.json_response({"error": "Missing topic_key"}, status=400)

    new_config = toggle_hidden_topic(topic_key)
    catalog = get_lecture_map()

    return web.json_response({
        "success": True,
        "hidden_topics": [str(h) for h in new_config.get("hidden_topics", [])],
        "topics": catalog.get("all_topics", catalog.get("topics", []))
    }, headers={"Access-Control-Allow-Origin": "*"})


async def api_admin_add_chapter(request):
    """Adds a new chapter and message range into catalog_config.json from the Mini App."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    category = body.get("category", "General Courses")
    subject = body.get("subject", "General Subject")
    chapter = body.get("chapter", "New Chapter")
    start_id = body.get("start_id")
    end_id = body.get("end_id")
    source_group = body.get("source_group")

    if not is_request_admin(user_id):
        return web.json_response({"error": "Unauthorized"}, status=403, headers={"Access-Control-Allow-Origin": "*"})

    if not start_id or not end_id:
        return web.json_response({"error": "start_id and end_id are required"}, status=400)

    add_curated_chapter(category, subject, chapter, [start_id, end_id], source_group)
    if main_client:
        await scan_master_forum(main_client)

    catalog = get_lecture_map()
    return web.json_response({
        "success": True,
        "topics": catalog.get("all_topics", catalog.get("topics", [])),
        "total_lectures": catalog.get("total_lectures", 0)
    }, headers={"Access-Control-Allow-Origin": "*"})


async def api_admin_rescan(request):
    """Triggers immediate re-indexing of Master Forum and catalog_config.json from UI."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    if not is_request_admin(user_id):
        return web.json_response({"error": "Unauthorized"}, status=403, headers={"Access-Control-Allow-Origin": "*"})

    if main_client:
        await scan_master_forum(main_client)

    catalog = get_lecture_map()
    return web.json_response({
        "success": True,
        "topics": catalog.get("all_topics", catalog.get("topics", [])),
        "total_lectures": catalog.get("total_lectures", 0)
    }, headers={"Access-Control-Allow-Origin": "*"})


# =================================================================
# TELEGRAM BOT COMMAND HANDLERS
# =================================================================

def setup_bot_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r'^/start'))
    async def start_handler(event):
        user_id = event.sender_id
        logger.info(f"👤 User /start from {user_id}")

        # Ensure user pinned data exists
        await get_or_create_user_data(client, user_id)

        # Check Force Subscribe (FSUB)
        is_sub = await check_user_subscribed(client, user_id)
        if not is_sub:
            join_url = FORCE_SUB_INVITE_LINK or f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}"
            fsub_text = (
                "🔒 **Access Locked: Channel Subscription Required!**\n\n"
                f"Is bot aur lectures ko access karne ke liye aapko hamare official channel ko join karna zaroori hai:\n"
                f"👉 **{FORCE_SUB_CHANNEL}**\n\n"
                "Channel join karne ke baad neeche diye gaye **'🔄 Verify & Start'** button par click karein."
            )
            bot_me = await client.get_me()
            bot_username = bot_me.username or "bot"
            buttons = [
                [Button.url("📢 Join Updates Channel", join_url)],
                [Button.url("🔄 Verify & Start", f"https://t.me/{bot_username}?start=verify")]
            ]
            await event.respond(fsub_text, buttons=buttons)
            return

        welcome_text = (
            "👋 **Welcome to Telegram Lecture Forwarder!**\n\n"
            "📚 Lectures are stored in high quality and forwarded directly into your personal private channel/group.\n\n"
            "⚡ **Quick 2-Step Setup:**\n"
            "1️⃣ Add this bot as an **Admin** in your private channel or group.\n"
            "2️⃣ Tap the **🚀 Lectures** button at the bottom of the chat, enter your channel username/ID in **Settings ⚙️**, and pick your lectures!\n\n"
            "⚠️ *Your progress & history is safely pinned in this chat. Please do not unpin it!*"
        )
        await event.respond(welcome_text)

    @client.on(events.NewMessage(pattern=r'^/rescan'))
    async def rescan_handler(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("⛔ **Access Denied!** Only the bot Admin can use `/rescan`.")
            return

        status_msg = await event.respond("🔄 Re-scanning master forum topics and lectures. Please wait...")
        scanned_catalog = await scan_master_forum(client)
        total_lecs = scanned_catalog.get("total_lectures", 0)
        topic_count = len(scanned_catalog.get("topics", []))
        await status_msg.edit(f"✅ Scan complete! {total_lecs} lectures indexed across {topic_count} topics.")

    @client.on(events.NewMessage(pattern=r'^/admin'))
    async def admin_handler(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("⛔ **Access Denied!** Only the bot Admin can access this menu.")
            return

        q = get_queue_status()
        users = get_all_registered_users()
        catalog = get_lecture_map()
        last_scanned = catalog.get("last_scanned") or "Never"

        text = (
            "👑 **Admin Dashboard**\n\n"
            f"👥 **Total Registered Students:** {len(users)}\n"
            f"📚 **Indexed Topics:** {len(catalog.get('topics', []))}\n"
            f"🎬 **Total Lectures:** {catalog.get('total_lectures', 0)}\n"
            f"🕒 **Last Rescan:** {last_scanned}\n\n"
            "⚡ **Queue Performance:**\n"
            f"• Queue Backlog: {q['backlog_count']} jobs\n"
            f"• Active Workers: {q['worker_count']}\n"
            f"• Busy Mode Active: {'YES' if q['is_busy'] else 'NO'}\n\n"
            "🛠️ **Admin Commands:**\n"
            "• `/broadcast <text>` - Send announcement to all students\n"
            "• `/rescan` - Re-index forum topics & catalog_config.json\n"
            "• `/status` - Queue health & bot performance"
        )
        await event.respond(text)

    @client.on(events.NewMessage(pattern=r'^/broadcast'))
    async def broadcast_handler(event):
        if ADMIN_ID and event.sender_id != ADMIN_ID:
            await event.respond("⛔ **Access Denied!** Only the bot Admin can broadcast announcements.")
            return

        reply_msg = await event.get_reply_message()
        broadcast_text = event.message.message[len('/broadcast'):].strip()

        if not reply_msg and not broadcast_text:
            await event.respond(
                "ℹ️ **How to Use /broadcast:**\n\n"
                "• Send: `/broadcast Your message here`\n"
                "• OR reply to any photo/video/document with `/broadcast`"
            )
            return

        users = get_all_registered_users()
        if not users:
            await event.respond("⚠️ No registered students found yet!")
            return

        status_msg = await event.respond(f"📢 Starting broadcast to {len(users)} student(s)...")

        success_count = 0
        blocked_count = 0

        for uid in users:
            try:
                if reply_msg:
                    await client.send_message(uid, reply_msg)
                else:
                    await client.send_message(uid, broadcast_text)
                success_count += 1
                await asyncio.sleep(0.05)
            except (errors.UserIsBlockedError, errors.InputUserDeactivatedError):
                blocked_count += 1
            except Exception as e:
                logger.debug(f"Broadcast failed for user {uid}: {e}")

        await status_msg.edit(
            "✅ **Broadcast Completed!**\n\n"
            f"• 👥 Total targeted: {len(users)}\n"
            f"• 📬 Successfully delivered: {success_count}\n"
            f"• 🚫 Blocked / Inactive: {blocked_count}"
        )

    @client.on(events.NewMessage(pattern=r'^/status'))
    async def status_handler(event):
        q = get_queue_status()
        catalog = get_lecture_map()
        text = (
            f"📊 **System Status:**\n"
            f"• Indexed Lectures: {catalog.get('total_lectures', 0)}\n"
            f"• Topics Scanned: {len(catalog.get('topics', []))}\n"
            f"• Active Workers: {q['worker_count']}\n"
            f"• Current Queue Backlog: {q['backlog_count']}\n"
            f"• High-Load Busy Mode: {'YES' if q['is_busy'] else 'NO'}"
        )
        await event.respond(text)


# =================================================================
# MAIN APPLICATION LIFECYCLE
# =================================================================

async def init_telegram_clients():
    """Initializes and logs in Main Bot and any Worker Bots using Bot Tokens."""
    global all_clients, main_client

    if not MAIN_BOT_TOKEN or not API_ID or not API_HASH:
        logger.error("Missing Telegram API_ID, API_HASH, or MAIN_BOT_TOKEN!")
        return

    # 1. Main Client
    main_client = TelegramClient('forwarder_main_session', API_ID, API_HASH)
    await main_client.start(bot_token=MAIN_BOT_TOKEN)
    all_clients.append(main_client)
    logger.info("🤖 Main Bot client successfully connected!")

    setup_bot_handlers(main_client)

    # Sync past registered users from backup channel
    try:
        await sync_users_from_backup_channel(main_client)
    except Exception as e:
        logger.debug(f"User sync warning: {e}")

    # 2. Worker Clients (Optional for multi-token 90 msg/sec scaling)
    for idx, token in enumerate(WORKER_BOT_TOKENS, start=1):
        try:
            worker_client = TelegramClient(f'forwarder_worker_{idx}_session', API_ID, API_HASH)
            await worker_client.start(bot_token=token)
            all_clients.append(worker_client)
            logger.info(f"🤖 Worker Bot #{idx} connected!")
        except Exception as e:
            logger.error(f"Failed to start Worker Bot #{idx} with token: {e}")

    # Initial scan of Master Forum
    try:
        await scan_master_forum(main_client)
    except Exception as e:
        logger.error(f"Initial forum scan warning: {e}. Bot will proceed to start web server.")

    # Start Queue Dispatcher background task
    asyncio.create_task(start_queue_workers(all_clients))

    # Configure Telegram persistent Mini App Menu button
    if WEBAPP_URL:
        try:
            from telethon.tl.functions.bots import SetBotMenuButtonRequest
            from telethon import types
            await main_client(SetBotMenuButtonRequest(
                user_id=types.InputUserEmpty(),
                button=types.BotMenuButton(text="🚀 Lectures", url=WEBAPP_URL)
            ))
            logger.info("📱 Configured Telegram persistent Mini App Menu button.")
        except Exception as e:
            logger.debug(f"Menu button note: {e}")


async def create_app():
    """Builds and configures the aiohttp web application."""
    app = web.Application()

    # REST Endpoints
    app.router.add_options("/{tail:.*}", handle_cors)
    app.router.add_get("/api/check_fsub", api_check_fsub)
    app.router.add_get("/api/lectures", api_get_lectures)
    app.router.add_get("/api/user_data", api_get_user_data)
    app.router.add_post("/api/save_settings", api_save_settings)
    app.router.add_post("/api/verify_destination", api_verify_destination)
    app.router.add_post("/api/queue_one", api_queue_one)
    app.router.add_post("/api/complete_batch", api_complete_batch)
    app.router.add_get("/api/queue_status", api_queue_status)
    app.router.add_get("/api/admin/info", api_admin_info)
    app.router.add_post("/api/admin/toggle_topic", api_admin_toggle_topic)
    app.router.add_post("/api/admin/add_chapter", api_admin_add_chapter)
    app.router.add_post("/api/admin/rescan", api_admin_rescan)

    # Serve Frontend static directory if present
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
    if os.path.exists(frontend_dir):
        logger.info(f"Serving static frontend files from: {frontend_dir}")
        async def index_handler(request):
            return web.FileResponse(os.path.join(frontend_dir, "index.html"))
        app.router.add_get("/", index_handler)
        app.router.add_static("/", path=frontend_dir, show_index=False)

    return app


async def main():
    await init_telegram_clients()
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    logger.info(f"🌐 Server running and listening at http://{HOST}:{PORT}")

    # Keep alive
    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
