import os
import json
import math
import logging
import asyncio
import datetime
from telethon import TelegramClient
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageActionTopicCreate
)

from config import FORUM_CHAT_ID, logger

# Cache for fast in-memory access by REST API
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lecture_map_cache.json")
LECTURE_MAP_CACHE = {
    "topics": [],
    "all_topics": [],
    "total_lectures": 0,
    "last_scanned": None
}

def get_lecture_map() -> dict:
    """Returns the live in-memory lecture catalog."""
    return LECTURE_MAP_CACHE

def update_lecture_cache(new_data: dict) -> dict:
    """Updates LECTURE_MAP_CACHE in-place so all references across modules stay synchronized."""
    LECTURE_MAP_CACHE.clear()
    LECTURE_MAP_CACHE.update(new_data)
    return LECTURE_MAP_CACHE

if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            disk_cache = json.load(f)
            if isinstance(disk_cache, dict) and "topics" in disk_cache:
                update_lecture_cache(disk_cache)
                logger.info(f"💾 Loaded cached lecture map from disk ({LECTURE_MAP_CACHE.get('total_lectures', 0)} lectures).")
    except Exception as e:
        logger.debug(f"Could not load disk cache: {e}")

LECTURE_MAP_PIN_TAG = "#LECTURE_MAP_STORAGE"


def get_real_file_info(message, sequence_num):
    """
    Extracts the real file name, size in MB, and media type from a message.
    Priority order for title:
    1. Original document/video file_name attribute
    2. Caption (if message has caption text)
    3. Auto-generated sequence fallback: 'Lecture 01'
    """
    file_name = None
    file_size_bytes = 0
    file_type = "unknown"

    if message.file:
        file_size_bytes = message.file.size or 0
        if message.file.name:
            file_name = message.file.name

    if not file_name and message.document:
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                file_name = attr.file_name
                break
            elif isinstance(attr, DocumentAttributeVideo):
                file_type = "video"

    # Priority 2: Use caption if file_name is missing or generic
    caption = (message.message or "").strip()
    generic_names = ["video.mp4", "document.pdf", "file", "document", ""]
    
    if caption and (not file_name or file_name.lower() in generic_names):
        # Use first line of caption as clean title
        title = caption.split("\n")[0].strip()
    elif file_name:
        title = file_name
    elif caption:
        title = caption.split("\n")[0].strip()
    else:
        # Priority 3: Fallback sequential numbering
        title = f"Lecture {sequence_num:02d}"

    # Calculate accurate MB
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2) if file_size_bytes > 0 else 0.0

    return {
        "title": title,
        "caption": caption,
        "file_name": file_name,
        "file_size_bytes": file_size_bytes,
        "file_size_mb": file_size_mb,
        "message_id": message.id
    }


def parse_chat_id(val, default_val=0):
    """Safely normalizes numeric or string chat IDs to integer when appropriate."""
    if val is None or val == "":
        return default_val
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("-100") or val.lstrip("-").isdigit():
            try:
                return int(val)
            except ValueError:
                return val
    return val


def load_catalog_config() -> dict:
    """
    Loads manual catalog curation from backend/catalog_config.json if present.
    Supports categories, subjects, message ranges, multi-source groups, and hidden topics.
    """
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_config.json"),
        os.path.join(os.getcwd(), "backend", "catalog_config.json"),
        os.path.join(os.getcwd(), "catalog_config.json")
    ]

    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"📋 Loaded custom catalog configuration from: {p}")
                if isinstance(data, list):
                    return {
                        "hidden_topics": [],
                        "categories": data,
                        "custom_topics": [],
                        "auto_detect_remaining": True
                    }
                elif isinstance(data, dict):
                    return {
                        "hidden_topics": data.get("hidden_topics", []),
                        "categories": data.get("categories", []),
                        "custom_topics": data.get("custom_topics", []),
                        "auto_detect_remaining": data.get("auto_detect_remaining", True)
                    }
            except Exception as e:
                logger.warning(f"Failed to parse {p}: {e}")

    return {
        "hidden_topics": [],
        "categories": [],
        "custom_topics": [],
        "auto_detect_remaining": True
    }


CATALOG_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_config.json")


def save_catalog_config(config: dict) -> bool:
    """Saves updated catalog configuration directly to disk."""
    try:
        with open(CATALOG_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Updated {CATALOG_CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save catalog config: {e}")
        return False


def toggle_hidden_topic(topic_identifier) -> dict:
    """Toggles a topic between hidden and visible in catalog_config.json and updates cache."""
    global LECTURE_MAP_CACHE
    config = load_catalog_config()
    hidden = list(config.get("hidden_topics", []))

    found = False
    new_hidden = []
    target_str = str(topic_identifier).strip().lower()
    for item in hidden:
        if str(item).strip().lower() == target_str:
            found = True
        else:
            new_hidden.append(item)

    if not found:
        if isinstance(topic_identifier, str) and topic_identifier.strip().lstrip("-").isdigit():
            new_hidden.append(int(topic_identifier.strip()))
        else:
            new_hidden.append(topic_identifier)

    config["hidden_topics"] = new_hidden
    save_catalog_config(config)

    # Immediately update in-memory cache
    hidden_set = {str(h).strip().lower() for h in new_hidden}
    all_topics = LECTURE_MAP_CACHE.get("all_topics", LECTURE_MAP_CACHE.get("topics", []))
    for t in all_topics:
        t_id = str(t.get("thread_id", "")).strip().lower()
        t_title = str(t.get("title", "")).strip().lower()
        t_cat = str(t.get("category", "")).strip().lower()
        t["is_hidden"] = (t_id in hidden_set) or (t_title in hidden_set) or (bool(t_cat) and t_cat in hidden_set)

    visible_topics = [t for t in all_topics if not t.get("is_hidden")]
    LECTURE_MAP_CACHE["topics"] = visible_topics
    LECTURE_MAP_CACHE["all_topics"] = all_topics
    LECTURE_MAP_CACHE["total_lectures"] = sum(t.get("lecture_count", 0) for t in visible_topics)
    return config


def add_curated_chapter(category_name: str, subject_name: str, chapter_name: str, msg_range: list, source_group=None) -> dict:
    """Appends a new curated chapter into categories hierarchy in catalog_config.json."""
    config = load_catalog_config()
    categories = config.setdefault("categories", [])

    target_cat = None
    for c in categories:
        if c.get("name", "").strip().lower() == category_name.strip().lower():
            target_cat = c
            break
    if not target_cat:
        target_cat = {"name": category_name.strip(), "subjects": []}
        categories.append(target_cat)

    subjects = target_cat.setdefault("subjects", [])
    target_subj = None
    for s in subjects:
        if s.get("name", "").strip().lower() == subject_name.strip().lower():
            target_subj = s
            break
    if not target_subj:
        target_subj = {"name": subject_name.strip(), "chapters": []}
        subjects.append(target_subj)

    start_id = min(int(msg_range[0]), int(msg_range[1]))
    end_id = max(int(msg_range[0]), int(msg_range[1]))
    new_chapter = {
        "name": chapter_name.strip(),
        "msg_range": [start_id, end_id]
    }
    if source_group:
        new_chapter["source_group"] = parse_chat_id(source_group)

    target_subj.setdefault("chapters", []).append(new_chapter)
    save_catalog_config(config)
    return config


def is_in_topic(msg, target_topic_id: int) -> bool:
    """Checks whether a message belongs to a specific forum thread/topic."""
    if not target_topic_id:
        return True
    if msg.id == target_topic_id:
        return True
    reply = getattr(msg, 'reply_to', None)
    if not reply:
        # In Telegram supergroups, General topic messages have no reply_to
        return target_topic_id == 1

    top_id = getattr(reply, 'reply_to_top_id', None)
    if top_id is not None:
        return top_id == target_topic_id

    if getattr(reply, 'forum_topic', False):
        return getattr(reply, 'reply_to_msg_id', None) == target_topic_id

    # Normal reply without forum_topic flag belongs to General (thread 1)
    return target_topic_id == 1


async def detect_max_message_id(client: TelegramClient, entity) -> int:
    """
    Finds the highest message ID in the group accurately:
    1. Tries direct latest message via client.get_messages(entity, limit=1).
    2. Fallback: Probes exponential IDs and binary searches the exact boundary so NO messages are truncated.
    """
    # Tier 1: Direct latest message
    try:
        latest = await client.get_messages(entity, limit=1)
        if latest and len(latest) > 0 and getattr(latest[0], 'id', None):
            logger.info(f"📍 Detected latest message ID: {latest[0].id}")
            return latest[0].id
    except Exception as e:
        logger.debug(f"Direct latest message probe note: {e}")

    # Tier 2: Exponential probe + Binary search
    try:
        probes = [10, 25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000]
        msgs = await client.get_messages(entity, ids=probes)
        valid = [m.id for m in msgs if m and getattr(m, 'id', None) and not getattr(m, 'empty', False)]

        if not valid:
            small_msgs = await client.get_messages(entity, ids=list(range(1, 15)))
            small_valid = [m.id for m in small_msgs if m and getattr(m, 'id', None) and not getattr(m, 'empty', False)]
            return max(small_valid) if small_valid else 100

        low = max(valid)
        high = None
        for p in probes:
            if p > low:
                high = p
                break
        if not high:
            high = low + 500

        # Binary search between low and high to find the exact top message ID
        while low < high:
            mid = (low + high + 1) // 2
            test_msgs = await client.get_messages(entity, ids=[mid])
            if test_msgs and test_msgs[0] and getattr(test_msgs[0], 'id', None) and not getattr(test_msgs[0], 'empty', False):
                low = mid
            else:
                high = mid - 1

        logger.info(f"📍 Binary search detected max message ID: {low}")
        return low
    except Exception as e:
        logger.warning(f"Error in max message ID detection: {e}")
        return 200


async def fetch_messages_by_ids(client: TelegramClient, entity, start_id: int, end_id: int) -> list:
    """Fetches messages by ID chunks of 100 without invoking restricted history APIs."""
    messages = []
    chunk_size = 100
    for chunk_start in range(start_id, end_id + 1, chunk_size):
        chunk_ids = list(range(chunk_start, min(chunk_start + chunk_size, end_id + 1)))
        try:
            msgs = await client.get_messages(entity, ids=chunk_ids)
            for m in msgs:
                if m and getattr(m, 'id', None) and not getattr(m, 'empty', False):
                    messages.append(m)
        except Exception as e:
            logger.debug(f"Chunk fetch notice: {e}")
    return messages


async def scan_chapter(client: TelegramClient, chapter: dict, default_chat_id: int):
    """
    Scans a single chapter or section using either:
    1. msg_range: [start_id, end_id] (e.g. [100, 145])
    2. message_ids: [101, 102, 105, ...]
    3. topic_id: forum thread ID
    All fetching is strictly ID-based to ensure 100% Telegram Bot API compatibility.
    """
    ch_name = chapter.get("name", "General")
    source_group = parse_chat_id(chapter.get("source_group"), default_chat_id)
    topic_id = chapter.get("topic_id")
    msg_range = chapter.get("msg_range")
    message_ids = chapter.get("message_ids")

    if not source_group:
        logger.warning(f"No source_group configured for chapter '{ch_name}'")
        return [], 0

    try:
        source_entity = await client.get_entity(source_group)
    except Exception as e:
        logger.warning(f"Could not get entity for source group {source_group}: {e}")
        return [], 0

    sections = []
    current_section = {
        "name": ch_name,
        "lectures": []
    }
    sequence_in_section = 1
    total_lectures = 0

    messages_to_process = []

    try:
        if message_ids and isinstance(message_ids, list):
            # Fetch specific list of message IDs (channels.getMessages is allowed for bots)
            raw_msgs = await client.get_messages(source_entity, ids=message_ids)
            messages_to_process = [m for m in raw_msgs if m and not getattr(m, 'empty', False)]
        elif msg_range and isinstance(msg_range, list) and len(msg_range) == 2:
            start_id = min(int(msg_range[0]), int(msg_range[1]))
            end_id = max(int(msg_range[0]), int(msg_range[1]))
            # Fetch by ID chunks (avoids GetHistoryRequest / GetRepliesRequest completely)
            messages_to_process = await fetch_messages_by_ids(client, source_entity, start_id, end_id)
        else:
            # Auto-detect message ID range in group and fetch via bot-compliant ID requests
            max_id = await detect_max_message_id(client, source_entity)
            # Add safety buffer of 30 IDs to ensure no trailing messages are cut off
            end_id = max_id + 30
            all_raw = await fetch_messages_by_ids(client, source_entity, 1, end_id)
            if topic_id:
                messages_to_process = [m for m in all_raw if is_in_topic(m, int(topic_id))]
            else:
                messages_to_process = all_raw

        for msg in messages_to_process:
            # 1. Detect subfolder text dividers if present
            if msg.message and not msg.media:
                text = msg.message.strip()
                if len(text) < 80:
                    clean_name = text.strip("-=*# \n")
                    if current_section["lectures"]:
                        sections.append(current_section)
                    sec_name = clean_name if (not ch_name or ch_name == "General") else (f"{ch_name} • {clean_name}" if clean_name else ch_name)
                    current_section = {
                        "name": sec_name or ch_name,
                        "lectures": []
                    }
                    sequence_in_section = 1
                    continue

            # 2. Detect media files
            if msg.media and (msg.video or msg.document):
                info = get_real_file_info(msg, sequence_in_section)
                lecture_item = {
                    "id": f"{source_group}_{msg.id}",
                    "message_id": msg.id,
                    "thread_id": topic_id or 0,
                    "from_chat": source_group,
                    "title": info["title"],
                    "caption": info["caption"],
                    "file_name": info["file_name"],
                    "file_size_mb": info["file_size_mb"],
                    "file_size_bytes": info["file_size_bytes"],
                    "sequence_num": sequence_in_section
                }
                current_section["lectures"].append(lecture_item)
                sequence_in_section += 1
                total_lectures += 1

    except Exception as e:
        logger.warning(f"Error reading messages for chapter '{ch_name}' (source {source_group}): {e}")

    if current_section["lectures"]:
        sections.append(current_section)

    # Group into dynamic batches: Target 5 parts, minimum 10 lectures per batch
    for s in sections:
        sec_lectures = s["lectures"]
        n_lecs = len(sec_lectures)
        if n_lecs == 0:
            s["batches"] = {}
            continue

        batch_size = max(10, math.ceil(n_lecs / 5)) if n_lecs > 10 else n_lecs
        batches = {}

        for idx, lec in enumerate(sec_lectures):
            b_idx = (idx // batch_size) + 1
            start_num = ((b_idx - 1) * batch_size) + 1
            end_num = min(b_idx * batch_size, n_lecs)
            b_label = f"Batch {start_num}-{end_num}"

            lec["batch_index"] = b_idx
            lec["batch_label"] = b_label

            if b_label not in batches:
                batches[b_label] = []
            batches[b_label].append(lec)

        s["batches"] = batches

    return sections, total_lectures


async def discover_forum_topics(client: TelegramClient, entity) -> list:
    """
    Discovers forum topics in the supergroup:
    1. Attempts GetForumTopicsRequest (works if running under a Telegram user account).
    2. If restricted for bot users, probes for MessageActionTopicCreate service messages using channels.getMessages.
    3. Always includes the General topic (thread ID 1).
    """
    discovered_topics = []
    seen_ids = set()

    # Tier 1: Try GetForumTopicsRequest (if user session)
    try:
        req = await client(GetForumTopicsRequest(
            peer=entity,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))
        raw_topics = getattr(req, "topics", [])
        for t in raw_topics:
            discovered_topics.append({"thread_id": t.id, "title": t.title})
            seen_ids.add(t.id)
        if discovered_topics:
            logger.info(f"🔍 Discovered {len(discovered_topics)} topics via GetForumTopicsRequest.")
            return discovered_topics
    except Exception as e:
        logger.debug(f"GetForumTopicsRequest note (bots cannot invoke this API directly): {e}")

    # Tier 2: Bot-compatible topic discovery via MessageActionTopicCreate service messages
    try:
        sample_ids = list(range(1, 150))
        msgs = await client.get_messages(entity, ids=sample_ids)
        for m in msgs:
            if m and getattr(m, 'action', None) and isinstance(m.action, MessageActionTopicCreate):
                t_title = getattr(m.action, 'title', f"Topic {m.id}")
                if m.id not in seen_ids:
                    discovered_topics.append({"thread_id": m.id, "title": t_title})
                    seen_ids.add(m.id)
        if discovered_topics:
            logger.info(f"🔍 Discovered {len(discovered_topics)} topic(s) via service messages.")
    except Exception as e:
        logger.debug(f"Topic probe notice: {e}")

    # Always ensure General topic is present
    if 1 not in seen_ids:
        discovered_topics.insert(0, {"thread_id": 1, "title": "General"})

    return discovered_topics


async def scan_master_forum(client: TelegramClient, forum_chat_id: int = FORUM_CHAT_ID):
    """
    Hybrid Scanning Engine:
    1. Loads manual curation from catalog_config.json (Coaching / Categories, Subjects, Message Ranges).
    2. Respects hidden_topics to exclude draft/testing topics.
    3. Auto-detects remaining forum topics from the Master Forum if auto_detect_remaining is True.
    4. Caches catalog in-memory and persists index to Master Forum pinned storage.
    """
    global LECTURE_MAP_CACHE
    logger.info(f"🔍 Starting Hybrid Master Forum scan (default chat: {forum_chat_id})...")

    config = load_catalog_config()
    hidden_topics_set = {str(h).strip().lower() for h in config.get("hidden_topics", [])}
    topics_data = []
    manually_covered_topics = set()

    def check_is_hidden(thread_id, title, category=None):
        if str(thread_id).strip().lower() in hidden_topics_set:
            return True
        if str(title).strip().lower() in hidden_topics_set:
            return True
        if category and str(category).strip().lower() in hidden_topics_set:
            return True
        return False

    # -------------------------------------------------------------
    # 1. Process Custom Categories & Hierarchical Subjects
    # -------------------------------------------------------------
    for cat in config.get("categories", []):
        cat_name = cat.get("name", "Category")
        for subj in cat.get("subjects", []):
            subj_title = subj.get("name", "Subject")
            subj_source = parse_chat_id(subj.get("source_group"), forum_chat_id)
            subj_thread_id = subj.get("topic_id", 0)
            if subj_thread_id:
                manually_covered_topics.add(subj_thread_id)

            subj_sections = []
            subj_count = 0

            chapters = subj.get("chapters", [])
            # If no explicit chapters array, subject itself can be a chapter
            if not chapters:
                chapters = [subj]

            for ch in chapters:
                ch_sections, ch_count = await scan_chapter(client, ch, subj_source)
                subj_sections.extend(ch_sections)
                subj_count += ch_count

            if subj_sections:
                is_hid = check_is_hidden(subj_thread_id, subj_title, cat_name)
                topics_data.append({
                    "thread_id": subj_thread_id,
                    "category": cat_name,
                    "title": subj_title,
                    "sections": subj_sections,
                    "lecture_count": subj_count,
                    "from_chat": subj_source,
                    "is_hidden": is_hid
                })
                logger.info(f"✅ Added curated subject: '{subj_title}' [{cat_name}] with {subj_count} lectures (hidden={is_hid}).")

    # -------------------------------------------------------------
    # 2. Process Flat Custom Topics (if configured)
    # -------------------------------------------------------------
    for c_top in config.get("custom_topics", []):
        top_title = c_top.get("title", "Topic")
        top_cat = c_top.get("category")
        top_source = parse_chat_id(c_top.get("source_group"), forum_chat_id)
        top_thread_id = c_top.get("thread_id", 0)
        if top_thread_id:
            manually_covered_topics.add(top_thread_id)

        top_sections = []
        top_count = 0
        chapters = c_top.get("chapters", [])
        if not chapters:
            chapters = [c_top]

        for ch in chapters:
            ch_sections, ch_count = await scan_chapter(client, ch, top_source)
            top_sections.extend(ch_sections)
            top_count += ch_count

        if top_sections:
            is_hid = check_is_hidden(top_thread_id, top_title, top_cat)
            topics_data.append({
                "thread_id": top_thread_id,
                "category": top_cat,
                "title": top_title,
                "sections": top_sections,
                "lecture_count": top_count,
                "from_chat": top_source,
                "is_hidden": is_hid
            })
            logger.info(f"✅ Added custom topic: '{top_title}' with {top_count} lectures (hidden={is_hid}).")

    # -------------------------------------------------------------
    # 3. Auto-Detect Remaining Topics from Forum Supergroup
    # -------------------------------------------------------------
    if config.get("auto_detect_remaining", True) and forum_chat_id:
        try:
            entity = await client.get_entity(forum_chat_id)
            raw_topics = await discover_forum_topics(client, entity)

            for t in raw_topics:
                thread_id = t["thread_id"]
                topic_title = t["title"]

                if thread_id in manually_covered_topics:
                    logger.info(f"⏩ Topic '{topic_title}' (ID {thread_id}) already curated in catalog_config.json")
                    continue

                logger.info(f"📂 Scanning topic: '{topic_title}' (thread {thread_id})...")

                auto_sections, auto_count = await scan_chapter(client, {
                    "name": "General",
                    "source_group": forum_chat_id,
                    "topic_id": thread_id
                }, forum_chat_id)

                if auto_sections:
                    is_hid = check_is_hidden(thread_id, topic_title, None)
                    topics_data.append({
                        "thread_id": thread_id,
                        "category": None,
                        "title": topic_title,
                        "sections": auto_sections,
                        "lecture_count": auto_count,
                        "from_chat": forum_chat_id,
                        "is_hidden": is_hid
                    })

        except Exception as e:
            logger.debug(f"Auto-scan forum topics note: {e}")

    # -------------------------------------------------------------
    # 4. Update In-Memory Cache and Pinned Summary in Forum Group
    # -------------------------------------------------------------
    visible_topics = [t for t in topics_data if not t.get("is_hidden")]
    total_visible_lectures = sum(t.get("lecture_count", 0) for t in visible_topics)

    update_lecture_cache({
        "topics": visible_topics,
        "all_topics": topics_data,
        "total_lectures": total_visible_lectures,
        "last_scanned": datetime.datetime.utcnow().isoformat()
    })

    logger.info(f"🎉 Catalog ready! Total topics: {len(topics_data)} ({len(visible_topics)} visible), Total lectures: {total_visible_lectures}")

    # Update pinned summary in Master Forum Group if possible
    if forum_chat_id:
        try:
            forum_entity = await client.get_entity(forum_chat_id)
            await save_lecture_map_to_forum_pin(client, forum_entity, LECTURE_MAP_CACHE)
        except Exception as e:
            logger.debug(f"Note: Could not update pinned storage in forum chat {forum_chat_id}: {e}")

    return LECTURE_MAP_CACHE


async def save_lecture_map_to_forum_pin(client: TelegramClient, entity, data: dict):
    """
    Saves/Updates the LECTURE_MAP.
    1. Saves locally to lecture_map_cache.json for instant disaster recovery.
    2. Updates or creates pinned message in the Forum Group using bot-compatible methods.
    """
    # 1. Save local backup to disk
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info(f"💾 Persisted lecture catalog cache to disk.")
    except Exception as e:
        logger.debug(f"Could not write local catalog cache file: {e}")

    # 2. Pin/Edit in Forum Supergroup
    try:
        summary_text = (
            f"{LECTURE_MAP_PIN_TAG}\n"
            f"📚 Total Topics: {len(data['topics'])}\n"
            f"🎬 Total Lectures Indexed: {data['total_lectures']}\n"
            f"🕒 Last Scanned: {data['last_scanned']}\n\n"
            f"⚠️ Bot uses this pinned index to serve lectures instantly."
        )

        from telethon.tl.functions.channels import GetFullChannelRequest
        target_msg_id = None
        try:
            full = await client(GetFullChannelRequest(entity))
            pinned_id = getattr(full.full_chat, 'pinned_msg_id', None)
            if pinned_id:
                # Fetching a message by its ID is allowed for bots (uses channels.getMessages)
                msgs = await client.get_messages(entity, ids=[pinned_id])
                if msgs and msgs[0] and msgs[0].message and LECTURE_MAP_PIN_TAG in msgs[0].message:
                    target_msg_id = pinned_id
        except Exception as fe:
            logger.debug(f"Could not check pinned msg via full chat: {fe}")

        if target_msg_id:
            await client.edit_message(entity, target_msg_id, summary_text)
            logger.info("📌 Updated existing LECTURE_MAP pinned message in Forum Group.")
        else:
            sent_msg = await client.send_message(entity, summary_text)
            try:
                await client.pin_message(entity, sent_msg.id, notify=False)
                logger.info("📌 Created and pinned new LECTURE_MAP message in Forum Group.")
            except Exception as pe:
                logger.debug(f"Note: Could not pin message (check bot pin permissions in group): {pe}")
    except Exception as e:
        logger.debug(f"Could not update pinned storage in forum: {e}")
