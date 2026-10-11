# 🚀 Telegram Lecture Forwarder Bot + Mini App (1K User Ready)

An asynchronous Telegram lecture forwarding platform designed to handle **1,000+ simultaneous students** with **< 10-second perceived delivery time**, **Zero-Database architecture (per-user pinned messages + private backup channel)**, **Optimistic UI**, **Adsterra ad monetization**, and **Multi-Token Round-Robin worker scaling**.

---

## 🌟 Key Highlights

* **100% Isolated Project:** Built cleanly in its own dedicated folder (`telegram-lecture-forwarder/`) without touching any other workspace projects.
* **Zero Database Hosting Costs:** Stores user settings, batch progress, and history inside per-user pinned messages in DM (`USER_DATA::{"completed_batches":[], ...}`).
* **Disaster-Proof Backup Channel:** Auto-recovers user progress if the student accidentally unpins or deletes their DM database message.
* **Divider Text Pattern for Storage:** No need to rename videos or edit captions! Group lectures under simple text messages like `📌 Main Lectures` or `📌 NCERT Line by Line` in your Master Forum Group topics.
* **Real Filename & Accurate Size:** Automatically extracts real filenames from Telegram documents/videos and computes exact file sizes in MB.
* **Optimistic UI Engine:** UI shows 15-20 MB/s download and 15-45 MB/s upload with instant "Sent ✓" status while real forwarding executes in background asyncio queue.
* **Adsterra Monetization Ready:** Calibrated 25-30 second batch dwell time with auto-refreshing Adsterra 300x250 banner and Social Bar integration for multiple impressions per batch.
* **Multi-Token Round-Robin (30 to 90 msg/sec):** Ready for 1 bot token now, expandable to 3 tokens anytime.
* **No Vercel Needed:** Full deployment guides included for Render, Cloudflare Pages, and Ubuntu VPS.

---

## 📁 Project Structure

```
telegram-lecture-forwarder/
├── backend/
│   ├── app.py                 # Telethon Bot engine + aiohttp REST API server
│   ├── config.py              # Environment configuration & rate limits
│   ├── scanner.py             # Forum topic & divider scanner -> LECTURE_MAP
│   ├── user_storage.py        # Pinned message DB manager & backup channel restore
│   ├── queue_manager.py       # Asyncio round-robin queue & FloodWait protection
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Configuration template
├── frontend/
│   ├── index.html             # Telegram Mini App with modern dark UI
│   ├── styles.css             # Glassmorphism, glowing gauges, and responsive styling
│   ├── app.js                 # Optimistic UI engine, fake speedometer, visibility handler
│   └── ads_config.js          # Adsterra ad cycler and script injection manager
├── GUIDE.md                   # Complete Master Guide (Deployments, Forum Setup, Adsterra)
└── README.md                  # Project overview
```

---

## ⚡ Quick Start

### 1. Backend Setup
1. Open terminal and navigate to `backend/`:
   ```bash
   cd telegram-lecture-forwarder/backend
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
3. Run the application:
   ```bash
   python app.py
   ```

### 2. Frontend
The backend serves the frontend statically at `http://localhost:8080` out-of-the-box!

---

## 📖 Complete Documentation
For detailed guides on:
* **How to arrange your Master Forum Group (with divider text messages)**
* **Step-by-step deployments on Render, Cloudflare Pages, or VPS**
* **Setting up Adsterra Banner & Social Bar with auto-refresh**
* **Queue mechanics and multi-token workers**

👉 **Check out [GUIDE.md](file:///c:/Users/Abhishek%20Pandey/Desktop/Anurag/antigravity/telegram-lecture-forwarder/GUIDE.md)**
