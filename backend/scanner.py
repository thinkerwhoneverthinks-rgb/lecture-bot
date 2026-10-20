import os
import json
import logging
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument
)

from config import FORUM_CHAT_ID, logger

# Cache for fast in-memory access by REST API
LECTURE_MAP_CACHE = {
    "topics": [],
    "total_lectures": 0,
    "last_scanned": None
}

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


async def scan_master_forum(client: TelegramClient, forum_chat_id: int = FORUM_CHAT_ID):
    """
    Scans the Forum Supergroup:
    - Fetches all forum topics (Biology, Physics, Chemistry, etc.)
    - Reads messages inside each topic
    - Detects text messages as Section / Subfolder Dividers (e.g. '📌 Main Lectures', 'NCERT Read')
    - Groups videos and files into organized sections and 5-lecture batches
    - Caches results and updates pinned storage in forum group
    """
    global LECTURE_MAP_CACHE
    if not forum_chat_id:
        logger.warning("FORUM_CHAT_ID not configured! Skipping forum scan.")
        return LECTURE_MAP_CACHE

    logger.info(f"🔍 Starting Master Forum scan on chat {forum_chat_id}...")

    try:
        entity = await client.get_entity(forum_chat_id)
    except Exception as e:
        logger.error(f"Failed to access forum chat {forum_chat_id}: {e}")
        return LECTURE_MAP_CACHE

    topics_data = []
    total_lectures_count = 0

    try:
        # Fetch forum topics using MTProto request
        forum_topics_req = await client(GetForumTopicsRequest(
            channel=entity,
            offset_date=0,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))
        raw_topics = forum_topics_req.topics
    except Exception as e:
        logger.warning(f"Could not fetch topics list via GetForumTopicsRequest: {e}. Will attempt direct scan.")
        raw_topics = []

    # If topics exist, iterate through each topic
    topic_list = []
    if raw_topics:
        for t in raw_topics:
            topic_list.append({
                "thread_id": t.id,
                "title": t.title
            })
    else:
        # Fallback default topics if group has single thread or general
        topic_list.append({"thread_id": None, "title": "General / All Lectures"})

    for topic in topic_list:
        thread_id = topic["thread_id"]
        topic_title = topic["title"]
        logger.info(f"📂 Scanning topic: '{topic_title}' (thread_id: {thread_id})...")

        sections = []
        current_section = {
            "name": "General",
            "lectures": []
        }
        sequence_in_section = 1

        # Fetch messages in topic (Telethon iter_messages with reply_to=thread_id)
        kwargs = {"entity": entity, "limit": 2000, "reverse": True}
        if thread_id:
            kwargs["reply_to"] = thread_id

        async for msg in client.iter_messages(**kwargs):
            # 1. Detect Text Separators (e.g., '📌 Main Lectures', 'NCERT', 'DPP')
            if msg.message and not msg.media:
                text = msg.message.strip()
                # Check if this text acts as a subfolder divider
                # Usually short titles, headers starting with emoji or dashes or < 60 chars
                if len(text) < 80:
                    clean_name = text.strip("-=*# \n")
                    if current_section["lectures"]:
                        sections.append(current_section)
                    current_section = {
                        "name": clean_name if clean_name else text,
                        "lectures": []
                    }
                    sequence_in_section = 1
                    continue

            # 2. Detect Media Files (Video, Document, Audio)
            if msg.media and (msg.video or msg.document):
                info = get_real_file_info(msg, sequence_in_section)
                lecture_item = {
                    "id": f"{thread_id or 0}_{msg.id}",
                    "message_id": msg.id,
                    "thread_id": thread_id,
                    "title": info["title"],
                    "caption": info["caption"],
                    "file_name": info["file_name"],
                    "file_size_mb": info["file_size_mb"],
                    "file_size_bytes": info["file_size_bytes"],
                    "batch_index": ((sequence_in_section - 1) // 5) + 1,
                    "batch_label": f"Batch {(((sequence_in_section - 1) // 5) * 5) + 1}-{(((sequence_in_section - 1) // 5) * 5) + 5}"
                }
                current_section["lectures"].append(lecture_item)
                sequence_in_section += 1
                total_lectures_count += 1

        if current_section["lectures"]:
            sections.append(current_section)

        # Organize into 5-lecture batches inside each section
        for s in sections:
            batches = {}
            for lec in s["lectures"]:
                b_label = lec["batch_label"]
                if b_label not in batches:
                    batches[b_label] = []
                batches[b_label].append(lec)
            s["batches"] = batches

        topics_data.append({
            "thread_id": thread_id,
            "title": topic_title,
            "sections": sections,
            "lecture_count": sum(len(s["lectures"]) for s in sections)
        })

    # Update in-memory cache
    import datetime
    LECTURE_MAP_CACHE = {
        "topics": topics_data,
        "total_lectures": total_lectures_count,
        "last_scanned": datetime.datetime.utcnow().isoformat()
    }

    logger.info(f"✅ Scan complete! Found {len(topics_data)} topics and {total_lectures_count} lectures.")

    # Save to Pinned Message in Forum Group
    await save_lecture_map_to_forum_pin(client, entity, LECTURE_MAP_CACHE)

    return LECTURE_MAP_CACHE


async def save_lecture_map_to_forum_pin(client: TelegramClient, entity, data: dict):
    """
    Saves/Updates the LECTURE_MAP in Pinned Message 1 of Forum Group.
    Survives bot restarts.
    """
    try:
        summary_text = (
            f"{LECTURE_MAP_PIN_TAG}\n"
            f"📚 Total Topics: {len(data['topics'])}\n"
            f"🎬 Total Lectures Indexed: {data['total_lectures']}\n"
            f"🕒 Last Scanned: {data['last_scanned']}\n\n"
            f"⚠️ Bot uses this pinned index to serve lectures instantly."
        )

        # Check existing pinned messages
        pinned = await client.get_messages(entity, filter=None, limit=5)
        target_msg = None
        for m in pinned:
            if m.message and LECTURE_MAP_PIN_TAG in m.message:
                target_msg = m
                break

        if target_msg:
            await client.edit_message(entity, target_msg.id, summary_text)
            logger.info("📌 Updated existing LECTURE_MAP pinned message in Forum Group.")
        else:
            sent_msg = await client.send_message(entity, summary_text)
            await client.pin_message(entity, sent_msg.id, notify=False)
            logger.info("📌 Created and pinned new LECTURE_MAP message in Forum Group.")
    except Exception as e:
        logger.warning(f"Could not pin LECTURE_MAP message in forum: {e}")
