import os
import json
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
    HOST,
    PORT,
    WEBAPP_URL,
    FORCE_SUB_CHANNEL,
    FORCE_SUB_INVITE_LINK,
    logger
)
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import UserNotParticipantError
from scanner import scan_master_forum, LECTURE_MAP_CACHE
from user_storage import (
    get_or_create_user_data,
    save_user_data
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
    return web.json_response(LECTURE_MAP_CACHE, headers={"Access-Control-Allow-Origin": "*"})


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


async def api_save_settings(request):
    """
    Updates the user's destination group, topic ID, and optional custom bot token.
    Enforces 1 channel per user limit.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = body.get("user_id")
    custom_group = body.get("custom_group")
    custom_topic = body.get("custom_topic")
    custom_bot_token = body.get("custom_bot_token")

    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)

    user_id = int(user_id)
    data = await get_or_create_user_data(main_client, user_id)

    # Clean destination group input (@channel, link, or integer chat id)
    if custom_group:
        custom_group = str(custom_group).strip()
        if "t.me/" in custom_group:
            custom_group = "@" + custom_group.split("t.me/")[-1].strip("/")

    data["custom_group"] = custom_group
    data["custom_topic"] = custom_topic
    data["custom_bot_token"] = custom_bot_token

    saved = await save_user_data(main_client, user_id, data)
    return web.json_response({"success": saved, "data": data}, headers={"Access-Control-Allow-Origin": "*"})


async def api_queue_one(request):
    """
    Enqueues a single lecture forward task from Master Forum to User's Destination Group.
    Called optimistically by frontend while UI displays fake upload.
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

    if not dest_chat:
        return web.json_response({
            "error": "No destination group set! Please configure your group in Settings first."
        }, status=400, headers={"Access-Control-Allow-Origin": "*"})

    # Put job in queue
    job = await add_forward_job(
        user_id=user_id,
        dest_chat=dest_chat,
        dest_topic=dest_topic,
        from_chat=FORUM_CHAT_ID,
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
            "2️⃣ Open the **Lecture Dashboard** below, enter your channel username/ID in **Settings ⚙️**, and pick your lectures!\n\n"
            "⚠️ *Your progress & history is safely pinned in this chat. Please do not unpin it!*"
        )

        # Open natively as a Telegram Mini App (inside Telegram instead of Chrome)
        try:
            from telethon import types
            web_button = types.KeyboardButtonWebView(text="🚀 Open Lecture Dashboard", url=WEBAPP_URL)
            markup = types.ReplyInlineMarkup(rows=[types.KeyboardButtonRow(buttons=[web_button])])
            await event.respond(welcome_text, buttons=markup)
        except Exception as e:
            logger.warning(f"Could not send native webview button: {e}. Falling back to standard URL.")
            buttons = [
                [Button.url("🚀 Open Lecture Dashboard", WEBAPP_URL)]
            ]
            await event.respond(welcome_text, buttons=buttons)

    @client.on(events.NewMessage(pattern=r'^/rescan'))
    async def rescan_handler(event):
        # Admin command to rescan forum
        status_msg = await event.respond("🔄 Re-scanning master forum topics and lectures. Please wait...")
        await scan_master_forum(client)
        await status_msg.edit(f"✅ Scan complete! {LECTURE_MAP_CACHE['total_lectures']} lectures indexed across {len(LECTURE_MAP_CACHE['topics'])} topics.")

    @client.on(events.NewMessage(pattern=r'^/status'))
    async def status_handler(event):
        q = get_queue_status()
        text = (
            f"📊 **System Status:**\n"
            f"• Indexed Lectures: {LECTURE_MAP_CACHE['total_lectures']}\n"
            f"• Topics Scanned: {len(LECTURE_MAP_CACHE['topics'])}\n"
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


async def create_app():
    """Builds and configures the aiohttp web application."""
    app = web.Application()

    # REST Endpoints
    app.router.add_options("/{tail:.*}", handle_cors)
    app.router.add_get("/api/check_fsub", api_check_fsub)
    app.router.add_get("/api/lectures", api_get_lectures)
    app.router.add_get("/api/user_data", api_get_user_data)
    app.router.add_post("/api/save_settings", api_save_settings)
    app.router.add_post("/api/queue_one", api_queue_one)
    app.router.add_post("/api/complete_batch", api_complete_batch)
    app.router.add_get("/api/queue_status", api_queue_status)

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
