import os
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

# User Registry for broadcasts & statistics
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registered_users.json")
REGISTERED_USERS = set()


def load_registered_users():
    global REGISTERED_USERS
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    REGISTERED_USERS = set(int(u) for u in data)
        except Exception as e:
            logger.warning(f"Could not load registered users from {USERS_FILE}: {e}")


load_registered_users()


def register_user(user_id: int):
    global REGISTERED_USERS
    if not user_id:
        return
    user_id = int(user_id)
    if user_id not in REGISTERED_USERS:
        REGISTERED_USERS.add(user_id)
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(REGISTERED_USERS), f)
        except Exception as e:
            logger.warning(f"Could not save registered users to {USERS_FILE}: {e}")


def get_all_registered_users() -> list:
    global REGISTERED_USERS
    return list(REGISTERED_USERS)


# Local persistent disk store for disaster recovery without triggering bot GetHistoryRequest restrictions
DATA_STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data_store.json")


def save_to_local_store(user_id: int, data: dict):
    """Saves user data locally on disk for zero-latency crash recovery."""
    try:
        store = {}
        if os.path.exists(DATA_STORE_FILE):
            with open(DATA_STORE_FILE, "r", encoding="utf-8") as f:
                store = json.load(f)
        store[str(user_id)] = data
        with open(DATA_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f)
    except Exception as e:
        logger.debug(f"Could not write to local user store: {e}")


def load_from_local_store(user_id: int) -> dict:
    """Loads user data snapshot from local store."""
    try:
        if os.path.exists(DATA_STORE_FILE):
            with open(DATA_STORE_FILE, "r", encoding="utf-8") as f:
                store = json.load(f)
            return store.get(str(user_id))
    except Exception as e:
        logger.debug(f"Could not read from local user store: {e}")
    return None


async def sync_users_from_backup_channel(client: TelegramClient):
    """
    Syncs registered users from local disk storage.
    Note: Telegram API restricts bot users from calling GetHistoryRequest on channels.
    """
    try:
        if os.path.exists(DATA_STORE_FILE):
            with open(DATA_STORE_FILE, "r", encoding="utf-8") as f:
                store = json.load(f)
            for uid_str in store.keys():
                if uid_str.isdigit():
                    register_user(int(uid_str))
        logger.info(f"👥 User registry initialized with {len(REGISTERED_USERS)} student(s).")
    except Exception as e:
        logger.debug(f"User sync note: {e}")


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
        # Fetch pinned messages or recent messages in user DM (Allowed for bot in 1-on-1 DM)
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
    Retrieves backup snapshot of user data.
    Checks memory cache and local persistent store.
    """
    if user_id in USER_CACHE:
        return USER_CACHE[user_id]
    return load_from_local_store(user_id)


async def backup_to_channel(client: TelegramClient, user_id: int, data: dict):
    """
    Sends a point-in-time snapshot to the private backup channel.
    (send_message is fully allowed for bot users)
    """
    save_to_local_store(user_id, data)
    if not BACKUP_CHANNEL_ID:
        return

    try:
        payload = serialize_user_data(data)
        backup_text = f"BACKUP::user_{user_id}::{PINNED_DB_TAG}{payload}"
        await client.send_message(BACKUP_CHANNEL_ID, backup_text)
    except Exception as e:
        logger.debug(f"Note: Backup snapshot post: {e}")


async def get_or_create_user_data(client: TelegramClient, user_id: int) -> dict:
    """
    Retrieves user data cleanly without spamming the user's private DM:
    1. Checks fast in-memory session cache.
    2. Checks persistent disk store (user_data_store.json).
    3. Migrates legacy pinned DM message if one exists, then removes the spam message from DM.
    4. Initializes default profile safely.
    """
    register_user(user_id)
    if user_id in USER_CACHE:
        return USER_CACHE[user_id]

    local_data = load_from_local_store(user_id)
    if local_data:
        USER_CACHE[user_id] = local_data
        return local_data

    # Check for legacy pinned message to migrate data from
    if client:
        try:
            msg, legacy_data = await find_pinned_data_message(client, user_id)
            if legacy_data:
                USER_CACHE[user_id] = legacy_data
                save_to_local_store(user_id, legacy_data)
                logger.info(f"Migrated legacy pinned user data for {user_id} to local disk store.")
                # Clean up the legacy raw JSON message from DM to stop spam
                try:
                    await client.delete_messages(user_id, [msg.id])
                except Exception:
                    pass
                return legacy_data
        except Exception as e:
            logger.debug(f"Legacy message check note for user {user_id}: {e}")

    # Brand new user initialization
    data = dict(DEFAULT_USER_DATA)
    USER_CACHE[user_id] = data
    save_to_local_store(user_id, data)
    logger.info(f"✨ Initialized clean persistent user storage for user {user_id}.")

    # Optional snapshot to private backup channel if configured
    if BACKUP_CHANNEL_ID and client:
        try:
            await backup_to_channel(client, user_id, data)
        except Exception:
            pass

    return data


async def save_user_data(client: TelegramClient, user_id: int, data: dict) -> bool:
    """
    Saves updated user data cleanly and instantly:
    - Updates in-memory session cache.
    - Writes directly to local persistent disk store (user_data_store.json).
    - Asynchronously writes snapshot to BACKUP_CHANNEL_ID (admin channel only).
    - NEVER sends or pins raw JSON dumps into the user's personal chat!
    """
    USER_CACHE[user_id] = data
    save_to_local_store(user_id, data)

    # Backup snapshot to admin backup channel if configured
    if BACKUP_CHANNEL_ID and client:
        try:
            await backup_to_channel(client, user_id, data)
        except Exception as e:
            logger.debug(f"Backup channel snapshot note: {e}")

    return True
