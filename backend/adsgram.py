import aiohttp
import logging
from telethon import Button, errors
from config import ADSGRAM_BLOCK_ID, ADSGRAM_TOKEN, logger

async def fetch_and_send_adsgram_ad(client, user_id: int) -> bool:
    """
    Fetches a native bot sponsored post from AdsGram and delivers it cleanly
    to the user's personal Bot PM (user_id) at the completion of a lecture batch.
    Never sends ads to groups or channels.
    """
    if not ADSGRAM_BLOCK_ID or ADSGRAM_BLOCK_ID.strip() in ("YOUR_ADSGRAM_BLOCK_ID_HERE", "YOUR_BLOCK_ID_HERE", ""):
        logger.debug(f"[AdsGram] No valid ADSGRAM_BLOCK_ID configured. Skipping ad delivery for user {user_id}.")
        return False

    clean_block_id = ADSGRAM_BLOCK_ID.strip().replace("bot-", "").replace("block-", "")

    # AdsGram advbot API query parameters (supports both tgid/blockid and userId/blockId schemas)
    params = {
        "blockid": clean_block_id,
        "blockId": clean_block_id,
        "tgid": str(user_id),
        "userId": str(user_id),
        "language": "en"
    }
    if ADSGRAM_TOKEN:
        params["token"] = ADSGRAM_TOKEN

    api_url = "https://api.adsgram.ai/advbot"

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"[AdsGram] API returned status {resp.status} for user {user_id}")
                    return False

                data = await resp.json()
                if not data:
                    return False

                # Support both { result: { ... } } and direct { text_html: ... } schemas
                ad = data.get("result") if (isinstance(data, dict) and data.get("result")) else data
                if not isinstance(ad, dict):
                    return False

                ad_text = ad.get("text_html") or ad.get("text") or "📢 <b>Sponsored Post</b>"
                banner_url = ad.get("image_url") or ad.get("bannerUrl") or ad.get("banner_url")
                button_text = ad.get("button_name") or ad.get("buttonText") or ad.get("button_text") or "Open Link"
                button_url = ad.get("click_url") or ad.get("buttonUrl") or ad.get("button_url")
                reward_url = ad.get("reward_url")
                reward_name = ad.get("button_reward_name") or "Claim Reward"

                buttons = []
                if button_url:
                    buttons.append(Button.url(button_text, button_url))
                if reward_url:
                    buttons.append(Button.url(reward_name, reward_url))

                # Structure buttons into rows
                inline_buttons = [[b] for b in buttons] if buttons else None

                # Send ad to user's personal Bot PM
                if banner_url:
                    try:
                        await client.send_file(
                            entity=user_id,
                            file=banner_url,
                            caption=ad_text,
                            buttons=inline_buttons,
                            parse_mode='html'
                        )
                        logger.info(f"📢 [AdsGram] Delivered image sponsored post to user {user_id} PM.")
                        return True
                    except Exception as img_err:
                        logger.warning(f"[AdsGram] Image send_file fallback ({img_err}). Sending text-only ad...")

                await client.send_message(
                    entity=user_id,
                    message=ad_text,
                    buttons=inline_buttons,
                    parse_mode='html'
                )
                logger.info(f"📢 [AdsGram] Delivered text sponsored post to user {user_id} PM.")
                return True

    except Exception as e:
        logger.debug(f"[AdsGram] Could not deliver ad to user {user_id}: {e}")
        return False


async def handle_batch_completion_delivery(client, user_id: int, custom_group: str, batch_title: str = None):
    """
    Enforces the routing rule upon batch completion:
    - Group Delivery: Lectures went to group. Sends clean completion notification + AdsGram Ad to user PM.
      NEVER sends ads to the study group!
    - PM Delivery: Lectures went to PM. Sends AdsGram Ad to user PM at the bottom of the batch.
    """
    is_group_delivery = bool(
        custom_group and str(custom_group).lower() not in ("none", "null", "pm", "me", "") and
        (str(custom_group).startswith("-100") or str(custom_group).lstrip("-").isdigit() or str(custom_group).startswith("@"))
    )

    batch_name_clean = batch_title or "your lectures"

    if is_group_delivery:
        # Group Delivery:
        # 1. Send clean notification to personal Bot PM
        notification_text = (
            f"🎉 <b>Batch Delivery Complete!</b>\n\n"
            f"All lectures for <b>{batch_name_clean}</b> have been successfully delivered to your study group/channel.\n\n"
            f"<i>Enjoy studying! Below is a message from our sponsor:</i>"
        )
        try:
            await client.send_message(user_id, notification_text, parse_mode='html')
        except Exception as e:
            logger.debug(f"Could not send PM completion notification to user {user_id}: {e}")

        # 2. Send AdsGram Sponsored Post to personal Bot PM
        await fetch_and_send_adsgram_ad(client, user_id)

    else:
        # Bot PM Delivery:
        # Append AdsGram Sponsored Post at the bottom of the batch in user PM
        await fetch_and_send_adsgram_ad(client, user_id)
