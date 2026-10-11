# 📘 Telegram Lecture Forwarder & Mini App — Master Guide

Welcome to the complete, end-to-end master documentation for **Telegram Lecture Forwarder**. This guide covers everything from deployment alternatives (without Vercel), monetization setup with Adsterra, how to arrange your Master Forum Group, and a deep-dive into every feature.

---

## 📑 Table of Contents
1. [Architecture & System Overview](#1-architecture--system-overview)
2. [Master Forum Group Setup Guide](#2-master-forum-group-setup-guide)
3. [Zero-Database Storage & Auto-Restore System](#3-zero-database-storage--auto-restore-system)
4. [Deployment Alternatives (No Vercel)](#4-deployment-alternatives-no-vercel)
   - [Option A: All-in-One Render Deployment (Recommended & Easiest)](#option-a-all-in-one-render-deployment)
   - [Option B: Cloudflare Pages (Frontend) + Render (Backend)](#option-b-cloudflare-pages-frontend--render-backend)
   - [Option C: Ubuntu VPS Deployment (Best for 1,000+ Concurrent Users)](#option-c-ubuntu-vps-deployment-best-for-1000-users)
5. [Adsterra Monetization & Ad Views Guide](#5-adsterra-monetization--ad-views-guide)
6. [Force Subscribe Channel (FSUB) Setup](#6-force-subscribe-channel-fsub-setup)
7. [Queue Engine & Multi-Bot Workers (1k User Ready)](#7-queue-engine--multi-bot-workers)
8. [Mini App Features & Optimistic UI](#8-mini-app-features--optimistic-ui)
9. [Bot Commands Reference](#9-bot-commands-reference)


---

## 1. Architecture & System Overview

This system allows 1,000+ simultaneous students to receive lecture videos and PDF documents in their private Telegram channels or groups with sub-10s perceived speed.

```
┌──────────────────────────────────────────────────────────┐
│                   TELEGRAM MINI APP                      │
│  - Optimistic UI (Fake Speedometer: 15-45 MB/s)          │
│  - Adsterra Sponsored Zone (Auto-cycling impressions)    │
│  - Visibility change detection (pauses if closed)        │
└────────────────────────────┬─────────────────────────────┘
                             │ REST API (/api/queue_one)
                             ▼
┌──────────────────────────────────────────────────────────┐
│                PYTHON BACKEND ENGINE                     │
│  - Fast asyncio.Queue with 0.05s dispatch                │
│  - Multi-Bot Round-Robin (1 to 3 Bot Tokens)             │
│  - Per-chat rate limiter (Max 20 msg/min per group)      │
└──────────────┬─────────────────────────────┬─────────────┘
               │ Forward Messages            │ Data Backup
               ▼                             ▼
┌──────────────────────────────┐ ┌─────────────────────────┐
│ MASTER FORUM STORAGE         │ │ PRIVATE BACKUP CHANNEL  │
│ - Topics (Biology, Physics)  │ │ - Automatic snapshots   │
│ - Text Divider Subfolders    │ │ - Instant recovery if   │
│ - Pinned LECTURE_MAP JSON    │ │   user unpins DM data   │
└──────────────────────────────┘ └─────────────────────────┘
```

---

## 2. Master Forum Group Setup Guide

Your Master Forum Group is your cloud storage library. Follow these steps to set it up perfectly:

### Step 1: Create the Forum Supergroup
1. Open Telegram and create a new **Group**.
2. Go to **Group Settings** -> **Chat Type** -> Make it **Private**.
3. In **Group Settings**, toggle **Topics = ON**. (This converts the group into a Forum).
4. Add your **Main Bot** (@your_bot) to this group and grant it **Full Admin Rights** (Send messages, Pin messages, Manage topics).

### Step 2: Create Topics (Subjects or Chapters)
Create topics inside the forum for each subject or chapter:
* Topic 1: `Biology`
* Topic 2: `Physics`
* Topic 3: `Chemistry`
*(Or individual chapter topics like `Living World`, `Optics`, `Genetics`).*

### Step 3: Posting Section Dividers & Dumping Lectures (The Divider Pattern)
You do **not** need to manually rename files or add captions! The bot handles videos and documents seamlessly using the **Text Divider Pattern**:

Inside any topic (e.g., `Biology`):
1. **Send a simple text message header:**
   ```text
   📌 Main Lectures
   ```
2. **Dump/Forward your 50 lecture videos or PDFs** directly after this text message.
   - The bot automatically assigns them to the subfolder `Main Lectures`.
   - The bot reads real document filenames (e.g., `Lec_01_Intro.mp4` or `Notes.pdf`).
   - If a video has no filename or caption, the bot automatically names it `Lecture 01 (245 MB)`, `Lecture 02 (180 MB)`.
3. **Send your next text message header:**
   ```text
   📌 NCERT Line by Line
   ```
4. **Dump the next 20 files.**
5. **Send your third text message header:**
   ```text
   📌 Questions & DPPs
   ```
6. **Dump the remaining 30 files.**

### Step 4: Indexing & Pinned LECTURE_MAP
* When the bot starts up, it scans all topics and text dividers.
* It automatically creates and pins a message tagged with `#LECTURE_MAP_STORAGE` in the Forum Group.
* Whenever you upload new lectures in the forum, simply send `/rescan` in DM with your bot to refresh the catalog!

---

## 3. Zero-Database Storage & Auto-Restore System

To eliminate database hosting costs (MongoDB, PostgreSQL) and simplify backups, Telegram itself serves as your database:

### How it Works:
1. When a user runs `/start`, the bot sends and pins a message in their DM:
   ```text
   ⚠️ DO NOT DELETE OR UNPIN - Ye aapka personal data hai. Delete karne par progress reset.

   USER_DATA::{"completed_batches":[],"sent_lectures":[],"custom_group":null,"custom_topic":null,"custom_bot_token":null}
   ```
2. **1-Channel Limit:** The user can bind only **1 destination channel or group**. This prevents multi-channel spam and keeps the JSON string tiny (< 300 characters, well under Telegram's 4,096 limit).
3. **Private Backup Channel Sync:** Every time a user completes a batch or updates settings, the bot writes an asynchronous snapshot to your private backup channel:
   ```text
   BACKUP::user_123456789::USER_DATA::{...}
   ```
4. **Auto-Restore Mechanism:** If the user accidentally deletes or unpins their message, opening the Mini App detects the missing pin, searches your backup channel, recreates and pins the message, and displays a friendly notice:
   *"⚠️ Aapne apna personal data message delete kar diya tha! Humne backup se wapas recover karke pin kar diya hai."*

---

## 4. Deployment Alternatives (No Vercel)

Since you do not wish to use Vercel, here are the **top 3 deployment options**:

---

### Option A: All-in-One Render Deployment (Recommended & Easiest)
*Render runs both the persistent Python backend server and serves the frontend Mini App from a single URL!*

1. **Sign up / Log in to [Render](https://render.com)** (Free tier available).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository containing the `telegram-lecture-forwarder` folder.
4. Set the following settings:
   - **Name:** `telegram-lecture-forwarder`
   - **Environment:** `Python 3`
   - **Root Directory:** `telegram-lecture-forwarder/backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
5. Click **Advanced** -> **Add Environment Variable** and add:
   - `API_ID`: Your API ID from my.telegram.org
   - `API_HASH`: Your API Hash from my.telegram.org
   - `MAIN_BOT_TOKEN`: Your bot token from @BotFather
   - `FORUM_CHAT_ID`: Your Forum Supergroup ID (e.g. `-1001234567890`)
   - `BACKUP_CHANNEL_ID`: Your private backup channel ID (e.g. `-1009876543210`)
   - `PORT`: `8080`
   - `WEBAPP_URL`: `https://your-service-name.onrender.com`
6. Click **Create Web Service**.
7. Once deployed, Render gives you a public URL (e.g. `https://telegram-lecture-forwarder.onrender.com`).
8. Open Telegram, message **@BotFather**:
   - Send `/mybots` -> Select your bot.
   - Go to **Bot Settings** -> **Menu Button** -> **Configure Menu Button**.
   - Set the URL to `https://your-service-name.onrender.com`.
   - Now, students clicking the menu button will open your Mini App instantly!

---

### Option B: Cloudflare Pages (Frontend) + Render (Backend)
*Best for lightning-fast frontend loading across the globe with 100% free Cloudflare CDN.*

1. **Deploy Backend on Render:**
   - Follow Option A above to deploy the backend on Render.
   - Note down your backend URL (e.g., `https://my-backend.onrender.com`).
2. **Deploy Frontend on Cloudflare Pages:**
   - Go to [Cloudflare Dashboard](https://dash.cloudflare.com) -> **Workers & Pages** -> **Create Application** -> **Pages**.
   - Connect your GitHub repository.
   - Set **Build output directory** to `telegram-lecture-forwarder/frontend`.
   - Click **Deploy**.
   - In `telegram-lecture-forwarder/frontend/app.js`, set `const API_BASE = "https://my-backend.onrender.com";`.
   - Your frontend URL will be `https://my-app.pages.dev`.

---

### Option C: Ubuntu VPS Deployment (Best for 1,000+ Concurrent Users)
*A $4/month VPS (from Hetzner, DigitalOcean, or Hostinger) gives you 24/7 dedicated CPU, zero restarts, and maximum speed.*

1. Connect to your VPS via SSH:
   ```bash
   ssh root@your_vps_ip
   ```
2. Install Python 3, Git, and Nginx:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-pip python3-venv nginx git
   ```
3. Clone your code:
   ```bash
   git clone <YOUR_REPO_URL> /var/www/telegram-forwarder
   cd /var/www/telegram-forwarder/telegram-lecture-forwarder/backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Create `.env` file with your credentials:
   ```bash
   nano .env
   ```
5. Set up **Systemd Service** for 24/7 uptime:
   ```bash
   sudo nano /etc/systemd/system/lecture-bot.service
   ```
   Paste:
   ```ini
   [Unit]
   Description=Telegram Lecture Forwarder Bot
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/var/www/telegram-forwarder/telegram-lecture-forwarder/backend
   ExecStart=/var/www/telegram-forwarder/telegram-lecture-forwarder/backend/venv/bin/python app.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
6. Start and enable service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable lecture-bot
   sudo systemctl start lecture-bot
   ```
7. Configure Nginx with SSL (Let's Encrypt Certbot) to point your domain (e.g., `bot.yourdomain.com`) to `http://localhost:8080`.

---

## 5. Adsterra Monetization & Ad Views Guide

### Safe Integration Rules for Telegram Mini Apps:
1. **Never use Aggressive Popunders / Auto-Redirects:** In Telegram WebViews, opening a new window can close or minimize the Mini App. This triggers `visibilitychange` and stops the download!
2. **Use High-Viewability Banners (300x250) & Social Bar:** These display natively below the progress bar and generate maximum dwell time.

### How to Get Your Adsterra Ad Tags:
1. Log in to your **[Adsterra Publisher Dashboard](https://adsterra.com)**.
2. Click **Websites** -> **Add Website**.
   - Enter your website domain (e.g., your Render or Cloudflare domain).
   - Select category (e.g., Books / Education / Streaming).
3. **Create Ad Unit 1: Banner 300x250**
   - Choose `300x250`.
   - **Crucial Setting:** Turn on **"Auto-refresh"** (set to 15 or 30 seconds). Every auto-refresh registers a **new paid impression** while the student watches the speedometer!
   - Copy the script URL or code snippet.
4. **Create Ad Unit 2: Social Bar (High CPM)**
   - Select `Social Bar`.
   - Copy the script code.

### Where to Insert Your Keys:
Open `telegram-lecture-forwarder/frontend/ads_config.js`:
```javascript
const ADS_CONFIG = {
    enabled: true,

    banner_300x250: {
        enabled: true,
        script_url: "//www.highperformanceformat.com/YOUR_300x250_KEY/invoke.js",
        container_id: "adsterra-banner-container",
        refresh_interval_sec: 25 // Auto-cycles ad every 25 seconds during batch
    },

    social_bar: {
        enabled: true,
        script_url: "//pl12345678.effectivegate.com/YOUR_SOCIAL_BAR_KEY.js"
    }
};
```

### Why Batch Speed is Calibrated to > 25 Seconds:
* Each 5-lecture batch takes **~28 seconds total** (3.2s download + 2.4s upload per lecture).
* This guarantees that during every single batch, the student views the ad for nearly half a minute, triggering **2 to 3 refreshed ad impressions per batch**!

---

## 6. Force Subscribe Channel (FSUB) Setup

Force Subscribe (FSUB) ensures that students must join your official Telegram updates channel or sponsor channel before they can use the bot or send lectures.

### How it Works:
1. **In Bot DM (`/start`):**
   - When a user starts the bot, it verifies their membership in your channel.
   - If not joined, the bot locks access and sends a direct message with:
     - 📢 **Join Updates Channel** button
     - 🔄 **Verify & Start** button
2. **In Mini App (Dashboard):**
   - Opening the Mini App calls `/api/check_fsub`.
   - If not subscribed, a sleek **🔒 Channel Subscription Required** locked modal appears over the interface.
   - Clicking "Send Batch" or calling `/api/queue_one` is blocked until verified.
   - Once the user joins and taps **"Verify Subscription"**, access is instantly unlocked!

### How to Configure FSUB:
1. Create a public or private Telegram Channel (e.g., `@MyOfficialChannel`).
2. Add your **Main Bot** (@your_bot) as an **Administrator** in your channel (with at least "Invite Users via Link" or basic admin permission so the bot has rights to check participant lists).
3. Open your `.env` file (or Render/VPS Environment Variables) and set:
   ```ini
   # Channel username (e.g. @MyOfficialChannel) or Chat ID (-100xxxx)
   FORCE_SUB_CHANNEL=@MyOfficialChannel

   # Public link or invite link
   FORCE_SUB_INVITE_LINK=https://t.me/MyOfficialChannel
   ```
4. **To Disable FSUB:** Simply leave `FORCE_SUB_CHANNEL=` blank! The bot will skip the check and grant open access to everyone.

---

## 7. Queue Engine & Multi-Bot Workers


Telegram enforces strict rate limits:
* **Per-chat limit:** Maximum **20 messages per minute** to the same group/channel.
* **Global limit:** Maximum **30 messages per second** across different chats per bot token.

### 3-Stage Scalable Bot Architecture:

#### Mode 1: Single Bot (Default Now)
* User only needs to add **1 Main Bot** (@your_bot) as Admin to their private channel.
* The backend queue dispatches jobs with a 0.05-second interval and enforces the 20 msg/min per-chat limit.
* 100 users forwarding 5 lectures each (500 messages) clear in ~16.6 seconds in the background.

#### Mode 2: Multi-Bot Workers (For 1,000+ Users)
* You can add hidden worker bot tokens in `.env`:
  ```ini
  WORKER_BOT_TOKENS=1111:worker_token_2,2222:worker_token_3
  ```
* The backend automatically initiates round-robin dispatch:
  - Job 1 -> Main Bot
  - Job 2 -> Worker Bot 1
  - Job 3 -> Worker Bot 2
* Capacity scales from **30 msgs/sec to 90 msgs/sec**! 1,000 simultaneous users clear in under 55 seconds!

#### Mode 3: Bring Your Own Bot (BYOB - Future Phase 3)
* The Mini App Settings includes an optional field: `Custom Bot Token (Phase 3 VIP)`.
* This token is already stored in the user's pinned DB schema (`"custom_bot_token": null`).

### Generic Busy Banner:
If the background queue backlog exceeds 5 items, the Mini App displays a generic, student-friendly banner without leaking internal queue counts:
> *"⏳ Bot is busy: Many students are sending lectures at the same time. Your lectures are queued and will be sent automatically. Please keep the Mini App open."*

---

## 8. Mini App Features & Optimistic UI

1. **Sub-10s Perceived Delivery:**
   - Lec 1 fake download (3.2s) -> immediate API call -> fake upload (2.4s) -> shows "Sent ✓".
   - Lec 2 starts immediately without waiting for real background delivery.
2. **Visibility Change Detection (`document.visibilitychange`):**
   - If the user minimizes Telegram, intervals pause and the current lecture progress resets to 0%.
   - Completed lectures in the batch remain saved.
   - Screen displays an alert prompting the user to keep the Mini App open.
3. **Hierarchical Navigation:**
   - Subjects -> Chapters -> Text Divider Subfolders (`📌 Main Lectures`, `📌 NCERT`) -> Batches (1-5, 6-10) -> Individual Lectures with MB size.
4. **Batch Jump Feature:**
   - If a student completed Batch 1-5 yesterday, Batch 1-5 displays as "Sent ✓" today, and a **"⚡ Jump to this"** button appears on Batch 6-10.

---

## 9. Bot Commands Reference

| Command | Who Can Use | Description |
| :--- | :--- | :--- |
| `/start` | Any Student | Initializes user DM pinned database message and presents the "Open Lecture Dashboard" Mini App button. |
| `/rescan` | Bot Owner / Admin | Re-scans all topics in the Master Forum Group, re-indexes lectures, and updates the pinned `#LECTURE_MAP_STORAGE`. |
| `/status` | Anyone | Displays real-time bot health, total indexed lectures, queue backlog, and worker count. |


---

*Enjoy ultra-fast lecture forwarding with zero database overhead and maximum ad monetization!*
