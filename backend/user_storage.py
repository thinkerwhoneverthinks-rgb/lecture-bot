import json
import logging
from telethon import TelegramClient
from config import (
    PINNED_DB_TAG,
    PINNED_DB_WARNING,
    DEFAULT_USER_DATA,
    BACKUP_CHANNEL_ID,
    logger
)

# In-memory session cache for fast lookup during high concurrency
USER_CACHE = {}


def serialize_user_data(data: dict) -> str:
    """Serializes user data dict into compact JSON format."""
    return json.dumps(data, separators=(',', ':'))


def parse_user_data_message(text: str) -> dict:
    """Extracts JSON data from a message containing PINNED_DB_TAG."""
    if not text or PINNED_DB_TAG not in text:
        return None
    try:
        raw_json = text.split(PINNED_DB_TAG, 1)[1].strip()
        return json.loads(raw_json)
    except Exception as e:
        logger.error(f"Error parsing user data JSON from message: {e}")
        return None


async def find_pinned_data_message(client: TelegramClient, user_id: int):
    """
    Looks for the pinned message in user DM that contains PINNED_DB_TAG.
    Returns (message_obj, parsed_data) or (None, None).
    """
    try:
        # Fetch pinned messages or recent messages in user DM
        messages = await client.get_messages(user_id, limit=20)
        for msg in messages:
            if msg.message and PINNED_DB_TAG in msg.message:
                parsed = parse_user_data_message(msg.message)
                if parsed:
                    return msg, parsed
    except Exception as e:
        logger.warning(f"Could not check pinned messages for user {user_id}: {e}")
    return None, None


async def search_backup_channel(client: TelegramClient, user_id: int) -> dict:
    """
    Searches the private backup channel for the latest data snapshot of user_id.
    Format in backup channel: BACKUP::user_{user_id}::USER_DATA::{json}
    """
    if not BACKUP_CHANNEL_ID:
        return None

    search_tag = f"BACKUP::user_{user_id}::{PINNED_DB_TAG}"
    try:
        async for msg in client.iter_messages(BACKUP_CHANNEL_ID, search=search_tag, limit=10):
            if msg.message and search_tag in msg.message:
                raw_json = msg.message.split(search_tag, 1)[1].strip()
                return json.loads(raw_json)
    except Exception as e:
        logger.warning(f"Failed to query backup channel for user {user_id}: {e}")

    return None


async def backup_to_channel(client: TelegramClient, user_id: int, data: dict):
    """Sends a point-in-time snapshot to the private backup channel."""
    if not BACKUP_CHANNEL_ID:
        return

    try:
        payload = serialize_user_data(data)
        backup_text = f"BACKUP::user_{user_id}::{PINNED_DB_TAG}{payload}"
        await client.send_message(BACKUP_CHANNEL_ID, backup_text)
    except Exception as e:
        logger.error(f"Failed to write snapshot to backup channel for user {user_id}: {e}")


async def get_or_create_user_data(client: TelegramClient, user_id: int) -> dict:
    """
    Retrieves user data:
    1. Checks user DM for pinned database message.
    2. If missing or deleted, searches private backup channel to restore.
    3. Recreates pinned message with recovered data + warning.
    4. If first-time user, initializes default database message and pins it.
    """
    if user_id in USER_CACHE:
        return USER_CACHE[user_id]

    msg, data = await find_pinned_data_message(client, user_id)

    if data:
        USER_CACHE[user_id] = data
        return data

    # Pinned message missing or deleted: Try to restore from backup channel
    recovered_data = await search_backup_channel(client, user_id)
    warning_text = ""

    if recovered_data:
        data = recovered_data
        warning_text = "⚠️ Aapne apna personal data message delete kar diya tha! Humne backup se wapas recover karke pin kar diya hai.\n\n"
        logger.info(f"🔄 Recovered deleted user data for user {user_id} from backup channel.")
    else:
        # Brand new user
        data = dict(DEFAULT_USER_DATA)
        logger.info(f"✨ Initializing brand new user storage for user {user_id}.")

    # Send and pin the data message in DM
    try:
        body = f"{warning_text}{PINNED_DB_WARNING}{PINNED_DB_TAG}{serialize_user_data(data)}"
        sent_msg = await client.send_message(user_id, body)
        await client.pin_message(user_id, sent_msg.id, notify=False)
        USER_CACHE[user_id] = data

        # Backup snapshot
        await backup_to_channel(client, user_id, data)
    except Exception as e:
        logger.error(f"Failed to pin user storage message in DM for user {user_id}: {e}")

    return data


async def save_user_data(client: TelegramClient, user_id: int, data: dict) -> bool:
    """
    Saves updated user data:
    - Edits pinned message in user DM.
    - Saves snapshot to backup channel.
    - Updates in-memory cache.
    """
    USER_CACHE[user_id] = data
    msg, _ = await find_pinned_data_message(client, user_id)

    serialized = serialize_user_data(data)
    full_text = f"{PINNED_DB_WARNING}{PINNED_DB_TAG}{serialized}"

    try:
        if msg:
            await client.edit_message(user_id, msg.id, full_text)
        else:
            sent_msg = await client.send_message(user_id, full_text)
            await client.pin_message(user_id, sent_msg.id, notify=False)

        # Write to backup channel asynchronously
        await backup_to_channel(client, user_id, data)
        return True
    except Exception as e:
        logger.error(f"Failed to update pinned database message for user {user_id}: {e}")
        return False
