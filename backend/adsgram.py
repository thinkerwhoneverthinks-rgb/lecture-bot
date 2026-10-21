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

    if not ADSGRAM_TOKEN:
        logger.warning(
            "⚠️ [AdsGram] ADSGRAM_TOKEN is not configured in .env / Render Environment Variables!\n"
            "AdsGram strictly requires your account token to fetch bot ads.\n"
            "To get it: AdsGram Dashboard -> Click Profile (top-right avatar) -> Copy Account Token -> Add ADSGRAM_TOKEN=... in Render."
        )
        # Deliver a clean sponsor notice so user verifies PM delivery routing works immediately
        fallback_text = (
            "📢 <b>Sponsored</b>\n\n"
            "🌟 <i>Study smarter! Find more high-yield lectures and notes in our updates channel.</i>"
        )
        try:
            await client.send_message(user_id, fallback_text, parse_mode='html')
            logger.info(f"📢 Delivered sponsor post to user {user_id} PM (awaiting ADSGRAM_TOKEN setup).")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send sponsor post to user {user_id}: {e}")
            return False

    clean_block_id = ADSGRAM_BLOCK_ID.strip().replace("bot-", "").replace("block-", "")

    # AdsGram advbot API query parameters
    params = {
        "blockid": clean_block_id,
        "blockId": clean_block_id,
        "tgid": str(user_id),
        "userId": str(user_id),
        "language": "en",
        "token": ADSGRAM_TOKEN.strip()
    }

    api_url = "https://api.adsgram.ai/advbot"

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, params=params) as resp:
                if resp.status != 200:
                    err_body = await resp.text()
                    logger.warning(f"⚠️ [AdsGram] API returned status {resp.status} for user {user_id}: {err_body}")
                    return False

                data = await resp.json()
                if not data:
                    logger.info(f"[AdsGram] Empty ad response from AdsGram for user {user_id}.")
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
        logger.error(f"❌ [AdsGram] Could not deliver ad to user {user_id}: {e}")
        return False


async def handle_batch_completion_delivery(client, user_id: int, custom_group: str, batch_title: str = None):
    """
    Enforces the routing rule upon batch completion:
    - Group Delivery: Lectures went to group. Sends clean completion notification + AdsGram Ad to user PM.
      NEVER sends ads to the study group!
    - PM Delivery: Lectures went to PM. Sends completion confirmation + AdsGram Ad to user PM at bottom of batch.
    """
    logger.info(f"📬 Executing completion delivery routing for user_id={user_id} (destination group={custom_group})...")

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
            logger.info(f"✅ Sent group delivery completion notice to user {user_id} PM.")
        except Exception as e:
            logger.error(f"❌ Failed to send PM completion notification to user {user_id}: {e}")

        # 2. Send AdsGram Sponsored Post to personal Bot PM
        await fetch_and_send_adsgram_ad(client, user_id)

    else:
        # Bot PM Delivery:
        # 1. Send clean completion confirmation in PM
        completion_text = (
            f"🎉 <b>Batch Delivery Complete!</b>\n\n"
            f"All lectures for <b>{batch_name_clean}</b> have been delivered to this chat. Happy learning! 📚"
        )
        try:
            await client.send_message(user_id, completion_text, parse_mode='html')
            logger.info(f"✅ Sent PM delivery completion notice to user {user_id} PM.")
        except Exception as e:
            logger.error(f"❌ Failed to send PM completion confirmation to user {user_id}: {e}")

        # 2. Append AdsGram Sponsored Post at the bottom of the batch in user PM
        await fetch_and_send_adsgram_ad(client, user_id)
