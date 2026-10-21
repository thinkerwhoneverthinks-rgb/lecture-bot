/**
 * Telegram Lecture Forwarder - Mini App Logic & Optimistic UI Engine
 */

// =================================================================
// 🛡️ SECURITY SHIELD: TELEGRAM-ONLY GUARD & ANTI-INSPECT PROTECTION
// =================================================================
(function() {
    'use strict';

    // 1. Telegram-Only Access Lock
    // Robust detection: checks for Telegram Webview Proxy (Android), iOS WebKit hook,
    // platform identifier, hash parameters, or cached SDK params.
    const tgApp = window.Telegram?.WebApp;
    const isTelegram = Boolean(
        window.TelegramWebviewProxy ||                           // Native Telegram Android WebView hook
        window.webkit?.messageHandlers?.webApp ||                // Native Telegram iOS WebView hook
        (tgApp?.platform && tgApp.platform !== 'unknown') ||    // Valid Telegram client platform (android, ios, tdesktop, etc.)
        tgApp?.initData ||                                       // Valid non-empty initData string
        location.hash.includes('tgWebAppData') ||               // URL fragment containing WebApp data
        location.hash.includes('tgWebAppPlatform') ||           // URL fragment containing Telegram platform
        location.hash.includes('tgWebAppVersion') ||            // URL fragment containing Telegram version
        sessionStorage.getItem('__telegram__initParams')        // Telegram SDK cached initParams
    );
    if (!isTelegram) {
        const renderBlock = () => {
            document.body.innerHTML = `
                <div class="security-block-screen">
                    <h2>🔒 Access Denied</h2>
                    <p>This application can only be accessed securely inside the official <strong>Telegram</strong> app.</p>
                </div>
            `;
        };
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', renderBlock);
        } else {
            renderBlock();
        }
        throw new Error("Direct browser access restricted.");
    }

    // 2. Block Right-Click Context Menu
    document.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        return false;
    }, true);

    // 3. Block Developer Tools & View-Source Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
        // F12
        if (e.key === 'F12' || e.keyCode === 123) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }

        const isCtrlOrMeta = e.ctrlKey || e.metaKey;
        const key = (e.key || '').toLowerCase();

        // Ctrl/Cmd + Shift + I/J/C (DevTools, Console, Inspector)
        if (isCtrlOrMeta && e.shiftKey && (key === 'i' || key === 'j' || key === 'c')) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }

        // Ctrl/Cmd + U (View Source), Ctrl/Cmd + S (Save Page)
        if (isCtrlOrMeta && (key === 'u' || key === 's')) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
    }, true);

    // 4. Debugger Trap (Detects and Freezes DevTools in Chrome/Edge)
    setInterval(() => {
        const start = performance.now();
        debugger;
        const end = performance.now();
        if (end - start > 100) {
            document.body.innerHTML = `
                <div class="security-block-screen">
                    <h2>⛔ Security Violation</h2>
                    <p>Developer inspection tools have been detected. Session terminated.</p>
                </div>
            `;
            setTimeout(() => window.location.reload(), 1000);
        }
    }, 600);

    // 5. DevTools Docked Window Dimension Sensor
    function checkDevToolsDimension() {
        const threshold = 160;
        const widthDiff = window.outerWidth - window.innerWidth > threshold;
        const heightDiff = window.outerHeight - window.innerHeight > threshold;
        if (widthDiff || heightDiff) {
            document.body.innerHTML = `
                <div class="security-block-screen">
                    <h2>⛔ Security Alert</h2>
                    <p>Inspection tools detected. Please close Developer Tools to continue.</p>
                </div>
            `;
        }
    }
    window.addEventListener('resize', checkDevToolsDimension);

    // 6. Neutralize Console
    try {
        const noop = () => {};
        ['log', 'debug', 'info', 'warn', 'error', 'dir', 'table'].forEach(fn => {
            window.console[fn] = noop;
        });
        Object.freeze(window.console);
    } catch (_) {}
})();

// =================================================================
// 🌗 THEME CONTROLLER (LIGHT & DARK MODE)
// =================================================================
let currentTheme = localStorage.getItem('app_theme') || (window.Telegram?.WebApp?.colorScheme === 'light' ? 'light' : 'dark');

function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('app_theme', theme);
    
    const themeBtn = document.getElementById('btn-theme-toggle');
    if (themeBtn) {
        themeBtn.textContent = theme === 'light' ? '☀️' : '🌙';
    }
    
    const tgInstance = window.Telegram?.WebApp;
    if (tgInstance) {
        const headerBg = theme === 'light' ? '#f1f5f9' : '#0a0d14';
        if (tgInstance.setHeaderColor) tgInstance.setHeaderColor(headerBg);
        if (tgInstance.setBackgroundColor) tgInstance.setBackgroundColor(headerBg);
    }
}

// 1. Initialize Telegram WebApp SDK
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    if (tg.enableClosingConfirmation) {
        tg.enableClosingConfirmation();
    }
    applyTheme(currentTheme);
}

// User Identification: Checks Telegram WebApp, URL parameters, hash data, and localStorage
const urlParams = new URLSearchParams(window.location.search);
const queryUserId = urlParams.get('user_id');

let resolvedUserId = tg?.initDataUnsafe?.user?.id;
if (!resolvedUserId && queryUserId && !isNaN(parseInt(queryUserId, 10))) {
    resolvedUserId = parseInt(queryUserId, 10);
}

// Fallback: extract user id from location.hash if embedded
if (!resolvedUserId && location.hash) {
    try {
        const hashMatch = decodeURIComponent(location.hash).match(/"id":\s*(\d+)/);
        if (hashMatch && hashMatch[1]) {
            resolvedUserId = parseInt(hashMatch[1], 10);
        }
    } catch (_) {}
}

if (resolvedUserId && resolvedUserId !== 123456789) {
    try { localStorage.setItem('cached_telegram_user_id', String(resolvedUserId)); } catch (_) {}
} else {
    try {
        const cached = localStorage.getItem('cached_telegram_user_id');
        if (cached && !isNaN(parseInt(cached, 10)) && parseInt(cached, 10) !== 123456789) {
            resolvedUserId = parseInt(cached, 10);
        }
    } catch (_) {}
}
const USER_ID = resolvedUserId || 123456789;

// API Base URL (auto-detects current host origin)
const API_BASE = window.location.origin;

// Application State
let appCatalog = null;
let userData = {
    completed_batches: [],
    sent_lectures: [],
    custom_group: null,
    custom_group_title: null,
    custom_topic: null,
    custom_bot_token: null
};

// =================================================================
// NAVIGATION STACK & BACK BUTTON ENGINE
// (Telegram WebApp Native BackButton + Android PopState Bridge)
// =================================================================
const navStack = [];
let isPoppingHistory = false;

function updateBackButtonVisibility() {
    if (tg?.BackButton) {
        if (navStack.length > 0) {
            tg.BackButton.show();
        } else {
            tg.BackButton.hide();
        }
    }
}

function pushNavState(viewId, closeCallback) {
    if (navStack.some(item => item.id === viewId)) return;

    navStack.push({ id: viewId, close: closeCallback });
    updateBackButtonVisibility();

    try {
        window.history.pushState({ modalView: viewId, timestamp: Date.now() }, '');
    } catch (e) {
        console.warn('history.pushState unavailable:', e);
    }
}

function popNavState(viewId, shouldPopBrowserHistory = true) {
    const idx = navStack.findIndex(item => item.id === viewId);
    if (idx !== -1) {
        navStack.splice(idx, 1);
        updateBackButtonVisibility();
    }

    if (shouldPopBrowserHistory && window.history.state?.modalView === viewId && !isPoppingHistory) {
        try {
            isPoppingHistory = true;
            window.history.back();
            setTimeout(() => { isPoppingHistory = false; }, 120);
        } catch (e) {
            isPoppingHistory = false;
        }
    }
}

function handleBackButtonPress() {
    if (navStack.length > 0) {
        const topItem = navStack.pop();
        updateBackButtonVisibility();
        if (topItem && typeof topItem.close === 'function') {
            topItem.close(false); // pass false to prevent double popHistory
        }
        return true;
    }
    return false;
}

// Telegram Native Back Button Handler (top header arrow & Android back button intercept)
if (tg?.BackButton) {
    tg.BackButton.onClick(() => {
        const handled = handleBackButtonPress();
        if (handled && window.history.state?.modalView && !isPoppingHistory) {
            try {
                isPoppingHistory = true;
                window.history.back();
                setTimeout(() => { isPoppingHistory = false; }, 120);
            } catch (e) {
                isPoppingHistory = false;
            }
        }
    });
}

// Android Hardware / Gesture Back Button via popstate
window.addEventListener('popstate', (e) => {
    if (isPoppingHistory) {
        isPoppingHistory = false;
        return;
    }
    if (navStack.length > 0) {
        const topItem = navStack.pop();
        updateBackButtonVisibility();
        if (topItem && typeof topItem.close === 'function') {
            topItem.close(false);
        }
    }
});

// Active Batch Queue State
let activeBatch = null;
let activeBatchLectures = [];
let currentLectureIndex = 0;
let isProcessingBatch = false;
let isPaused = false;
let speedInterval = null;
let currentLectureTimeout = null;

// DOM Elements
const destDisplayName = document.getElementById('dest-display-name');
const alertBusy = document.getElementById('alert-busy');
const alertPaused = document.getElementById('alert-paused');
const activeBatchLabel = document.getElementById('active-batch-label');
const speedStatusPill = document.getElementById('speed-status-pill');
const downloadSpeedVal = document.getElementById('download-speed-val');
const uploadSpeedVal = document.getElementById('upload-speed-val');
const currentLectureName = document.getElementById('current-lecture-name');
const batchProgressBar = document.getElementById('batch-progress-bar');
const batchProgressPercent = document.getElementById('batch-progress-percent');
const topicsTreeContainer = document.getElementById('topics-tree-container');
const lectureSearchInput = document.getElementById('lecture-search');

// Settings Modal DOM Elements
const settingsModal = document.getElementById('settings-modal');
const btnSettings = document.getElementById('btn-settings');
const btnEditDest = document.getElementById('btn-edit-dest');
const modalCloseBtn = document.getElementById('modal-close-btn');
const settingsForm = document.getElementById('settings-form');
const inputGroup = document.getElementById('input-group');
const inputTopic = document.getElementById('input-topic');
const inputBotToken = document.getElementById('input-bot-token');
const btnVerifyDest = document.getElementById('btn-verify-dest');
const destVerifyStatus = document.getElementById('dest-verify-status');
const btnRefresh = document.getElementById('btn-refresh');

// Force Subscribe DOM Elements
const fsubModal = document.getElementById('fsub-modal');
const btnFsubJoin = document.getElementById('btn-fsub-join');
const btnFsubVerify = document.getElementById('btn-fsub-verify');
let isForceSubscribed = true;

// Admin Dashboard DOM Elements
const btnAdminPanel = document.getElementById('btn-admin-panel');
const adminModal = document.getElementById('admin-modal');
const adminModalCloseBtn = document.getElementById('admin-modal-close-btn');
const adminIdBadge = document.getElementById('admin-id-badge');
const adminNavBtns = document.querySelectorAll('.admin-nav-btn');
const adminTabPanes = document.querySelectorAll('.admin-tab-pane');
const adminStatStudents = document.getElementById('admin-stat-students');
const adminStatLectures = document.getElementById('admin-stat-lectures');
const adminStatTopics = document.getElementById('admin-stat-topics');
const adminStatQueue = document.getElementById('admin-stat-queue');
const adminLastScanned = document.getElementById('admin-last-scanned');
const btnAdminRescanTrigger = document.getElementById('btn-admin-rescan-trigger');
const adminTopicSearch = document.getElementById('admin-topic-search');
const adminTopicsList = document.getElementById('admin-topics-list');
const adminCurateForm = document.getElementById('admin-curate-form');
const curateCategory = document.getElementById('curate-category');
const curateSubject = document.getElementById('curate-subject');
const curateChapter = document.getElementById('curate-chapter');
const curateStartId = document.getElementById('curate-start-id');
const curateEndId = document.getElementById('curate-end-id');
const curateSourceGroup = document.getElementById('curate-source-group');
const btnCurateSubmit = document.getElementById('btn-curate-submit');
let isAdmin = false;
let adminCachedData = null;


// =================================================================
// 2. INITIALIZATION & DATA FETCHING
// =================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Setup event listeners
    setupEventListeners();

    // Check Force Subscribe requirement
    await checkForceSubscribe();

    // Check Admin status (activates in-app admin suite if USER_ID == ADMIN_ID)
    await checkAdminStatus();

    // Load initial data
    await loadUserData();
    await loadCatalog();

    // Check backend queue health periodically
    checkQueueStatus();
    setInterval(checkQueueStatus, 10000);
});

function setupEventListeners() {
    // Theme toggle button
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    if (btnThemeToggle) {
        btnThemeToggle.addEventListener('click', () => {
            const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
            applyTheme(nextTheme);
        });
    }

    // Settings modal triggers
    btnSettings.addEventListener('click', openSettingsModal);
    btnEditDest.addEventListener('click', openSettingsModal);
    modalCloseBtn.addEventListener('click', closeSettingsModal);
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) closeSettingsModal();
    });

    // In-modal Back Arrow Buttons
    const modalBackArrowBtn = document.getElementById('modal-back-arrow-btn');
    if (modalBackArrowBtn) {
        modalBackArrowBtn.addEventListener('click', closeSettingsModal);
    }
    const adminModalBackArrowBtn = document.getElementById('admin-modal-back-arrow-btn');
    if (adminModalBackArrowBtn) {
        adminModalBackArrowBtn.addEventListener('click', closeAdminModal);
    }

    // Force Subscribe Verify Button
    if (btnFsubVerify) {
        btnFsubVerify.addEventListener('click', async () => {
            btnFsubVerify.textContent = 'Checking...';
            btnFsubVerify.disabled = true;
            const sub = await checkForceSubscribe();
            btnFsubVerify.textContent = '🔄 Verify Subscription';
            btnFsubVerify.disabled = false;
            if (sub) {
                alert('✅ Verification Successful! Access unlocked.');
            } else {
                alert('❌ Subscription not detected yet. Please join the channel and try again.');
            }
        });
    }

    settingsForm.addEventListener('submit', handleSaveSettings);

    if (btnVerifyDest) {
        btnVerifyDest.addEventListener('click', handleVerifyDestination);
    }

    if (inputGroup) {
        inputGroup.addEventListener('input', () => {
            const val = inputGroup.value.trim();
            // Match public topic with message: /<username>/<topic_id>/<msg_id>
            const mPublic = val.match(/t\.me\/[a-zA-Z0-9_]+\/(\d+)\/(\d+)/);
            if (mPublic && mPublic[1]) {
                inputTopic.value = mPublic[1];
            }
            // Match private topic with message: /c/<channel_id>/<topic_id>/<msg_id>
            const mPrivate = val.match(/t\.me\/c\/\d+\/(\d+)\/(\d+)/);
            if (mPrivate && mPrivate[1]) {
                inputTopic.value = mPrivate[1];
            }
            // Match private topic link without msg_id: /c/<channel_id>/<topic_id>
            const mTopicOnly = val.match(/t\.me\/c\/\d+\/(\d+)$/);
            if (mTopicOnly && mTopicOnly[1]) {
                inputTopic.value = mTopicOnly[1];
            }
        });
    }

    btnRefresh.addEventListener('click', async () => {
        await loadUserData();
        await loadCatalog();
    });

    // Search input
    lectureSearchInput.addEventListener('input', handleSearchFilter);

    // Admin Dashboard triggers & tabs
    if (btnAdminPanel) {
        btnAdminPanel.addEventListener('click', openAdminModal);
    }
    if (adminModalCloseBtn) {
        adminModalCloseBtn.addEventListener('click', closeAdminModal);
    }
    if (adminModal) {
        adminModal.addEventListener('click', (e) => {
            if (e.target === adminModal) closeAdminModal();
        });
    }

    // Admin Tabs switcher
    adminNavBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            adminNavBtns.forEach(b => b.classList.remove('active'));
            adminTabPanes.forEach(pane => {
                pane.classList.remove('active');
                pane.style.display = 'none';
            });
            btn.classList.add('active');
            const activePane = document.getElementById(targetTab);
            if (activePane) {
                activePane.classList.add('active');
                activePane.style.display = 'block';
            }
        });
    });

    // Admin Re-Scan button
    if (btnAdminRescanTrigger) {
        btnAdminRescanTrigger.addEventListener('click', handleAdminRescan);
    }

    // Admin Topic Search Filter
    if (adminTopicSearch) {
        adminTopicSearch.addEventListener('input', () => {
            if (adminCachedData) {
                renderAdminTopicsList(adminCachedData.topics || [], adminCachedData.hidden_topics || []);
            }
        });
    }

    // Admin Add Chapter Form
    if (adminCurateForm) {
        adminCurateForm.addEventListener('submit', handleCurateSubmit);
    }

    // Visibility Change Handling (Key requirement: Stop progress when app is closed/hidden)
    document.addEventListener('visibilitychange', handleVisibilityChange);
}


// =================================================================
// 3. VISIBILITY CHANGE HANDLER (APP MINIMIZE / BACKGROUND)
// =================================================================

function handleVisibilityChange() {
    // Background forwarding enabled:
    // With server-side background queueing, users can safely minimize or close the app anytime!
}


// =================================================================
// 4. API CALLS & USER STORAGE SYNC
// =================================================================

async function loadUserData() {
    try {
        const res = await fetch(`${API_BASE}/api/user_data?user_id=${USER_ID}`);
        if (res.ok) {
            userData = await res.json();
            updateDestinationUI();
        }
    } catch (e) {
        console.warn('Could not load user data from backend:', e);
    }
}

async function loadCatalog() {
    try {
        const res = await fetch(`${API_BASE}/api/lectures`);
        if (res.ok) {
            appCatalog = await res.json();
            renderCatalog(appCatalog);
        } else {
            showMockCatalog();
        }
    } catch (e) {
        console.warn('Could not connect to live backend. Rendering demo catalog:', e);
        showMockCatalog();
    }
}

async function checkQueueStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/queue_status`);
        if (res.ok) {
            const data = await res.json();
            // Show student-friendly generic busy alert if queue is overloaded
            if (data.is_busy) {
                alertBusy.style.display = 'flex';
            } else {
                alertBusy.style.display = 'none';
            }
        }
    } catch (e) {
        // Silent fail
    }
}

async function checkForceSubscribe() {
    try {
        const res = await fetch(`${API_BASE}/api/check_fsub?user_id=${USER_ID}`);
        if (res.ok) {
            const data = await res.json();
            if (data.required && !data.is_subscribed) {
                isForceSubscribed = false;
                if (btnFsubJoin && data.channel_url) {
                    btnFsubJoin.href = data.channel_url;
                }
                if (fsubModal) {
                    fsubModal.classList.add('active');
                }
                return false;
            } else {
                isForceSubscribed = true;
                if (fsubModal) {
                    fsubModal.classList.remove('active');
                }
                return true;
            }
        }
    } catch (e) {
        console.warn('Could not check force subscribe status:', e);
    }
    return true;
}

function updateDestinationUI() {
    if (userData.custom_group) {
        const topicSuffix = userData.custom_topic ? ` (Topic ${userData.custom_topic})` : '';
        const groupLabel = userData.custom_group_title 
            ? `${userData.custom_group_title} (${userData.custom_group})` 
            : userData.custom_group;
        destDisplayName.textContent = `${groupLabel}${topicSuffix}`;
        inputGroup.value = userData.custom_group;
    } else {
        destDisplayName.textContent = 'Bot PM (Default)';
        inputGroup.value = '';
    }

    if (userData.custom_topic) {
        inputTopic.value = userData.custom_topic;
    } else {
        inputTopic.value = '';
    }
    if (userData.custom_bot_token) {
        inputBotToken.value = userData.custom_bot_token;
    }
}


// =================================================================
// 5. OPTIMISTIC FORWARDING & SPEEDOMETER ENGINE
// =================================================================

/**
 * Starts a lecture batch with realistic speeds:
 * - Each batch takes > 25 seconds total for optimal ad impression dwell time.
 * - Download: 15-20 MB/s (takes ~3.2s)
 * - Immediate /api/queue_one background call
 * - Upload: 15-45 MB/s (takes ~2.4s)
 * - Instant "Sent ✓"
 */
async function startBatchForward(topicTitle, sectionName, batchLabel, lectures) {
    if (!isForceSubscribed) {
        const sub = await checkForceSubscribe();
        if (!sub) return;
    }

    // If destination is not configured, deliver directly to Bot PM (Default)
    if (!userData.custom_group) {
        console.log('[Forward] No custom group set; forwarding directly to Bot PM (Default)');
    }

    if (isProcessingBatch) {
        alert('A batch is already being forwarded! Please let it finish.');

        return;
    }

    isProcessingBatch = true;
    isPaused = false;
    activeBatch = {
        key: `${topicTitle}_${sectionName}_${batchLabel}`,
        topicTitle,
        sectionName,
        batchLabel
    };
    activeBatchLectures = lectures;
    currentLectureIndex = 0;

    // UI Updates
    activeBatchLabel.textContent = `${sectionName} • ${batchLabel}`;
    speedStatusPill.textContent = 'Sending...';
    speedStatusPill.className = 'status-pill status-active';

    // Process lectures in batch sequentially
    processNextLectureInBatch();
}

function processNextLectureInBatch() {
    if (isPaused) return;

    if (currentLectureIndex >= activeBatchLectures.length) {
        // Whole batch completed!
        completeCurrentBatch();
        return;
    }

    const lecture = activeBatchLectures[currentLectureIndex];
    currentLectureName.textContent = `Lec ${currentLectureIndex + 1}/${activeBatchLectures.length}: ${lecture.title}`;

    // Update overall batch progress bar
    const totalCount = activeBatchLectures.length;
    const pct = Math.round((currentLectureIndex / totalCount) * 100);
    batchProgressBar.style.width = `${pct}%`;
    batchProgressPercent.textContent = `${pct}%`;

    // Snappy phase: quick 200ms download and 250ms upload per lecture
    startSpeedInterval(45, 95, 'download');

    currentLectureTimeout = setTimeout(async () => {
        // Immediate optimistic API Call to backend queue
        triggerBackgroundQueue(lecture);

        startSpeedInterval(45, 95, 'upload');

        currentLectureTimeout = setTimeout(() => {
            // Mark this lecture sent in UI
            markLectureUICompleted(lecture.id);

            // Advance to next lecture
            currentLectureIndex++;
            processNextLectureInBatch();

        }, 250); // 0.25 sec upload

    }, 200); // 0.20 sec download
}

async function triggerBackgroundQueue(lecture) {
    try {
        await fetch(`${API_BASE}/api/queue_one`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                lecture_id: lecture.id,
                message_id: lecture.message_id,
                thread_id: lecture.thread_id,
                from_chat: lecture.from_chat,
                title: lecture.title
            })
        });
    } catch (e) {
        console.warn('Queue API error (handled gracefully):', e);
    }
}

async function completeCurrentBatch() {
    stopSpeedInterval();
    isProcessingBatch = false;

    // 100% Progress
    batchProgressBar.style.width = '100%';
    batchProgressPercent.textContent = '100%';
    speedStatusPill.textContent = 'Queued ✓';
    speedStatusPill.className = 'status-pill status-idle';
    downloadSpeedVal.textContent = '0.00 MB/s';
    uploadSpeedVal.textContent = '0.00 MB/s';
    currentLectureName.textContent = 'Batch enqueued! Forwarding in Telegram. You can close this app.';

    // Save batch completion in user's pinned DB
    if (activeBatch) {
        userData.completed_batches.push(activeBatch.key);
        try {
            await fetch(`${API_BASE}/api/complete_batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: USER_ID,
                    batch_key: activeBatch.key,
                    batch_label: activeBatch.batchLabel,
                    topic_title: activeBatch.topicTitle
                })
            });
        } catch (e) {}

        // Re-render UI to unlock next batch
        renderCatalog(appCatalog);
    }

    // Telegram Haptic feedback
    if (tg?.HapticFeedback) {
        tg.HapticFeedback.notificationOccurred('success');
    }
}

function startSpeedInterval(min, max, mode) {
    stopSpeedInterval();
    speedInterval = setInterval(() => {
        const val = ((Math.random() * (max - min)) + min).toFixed(2);
        if (mode === 'download') {
            downloadSpeedVal.textContent = `${val} MB/s`;
            uploadSpeedVal.textContent = '0.00 MB/s';
        } else {
            downloadSpeedVal.textContent = '0.00 MB/s';
            uploadSpeedVal.textContent = `${val} MB/s`;
        }
    }, 150);
}

function stopSpeedInterval() {
    if (speedInterval) {
        clearInterval(speedInterval);
        speedInterval = null;
    }
}

function markLectureUICompleted(lectureId) {
    const el = document.getElementById(`lec-status-${lectureId}`);
    if (el) {
        el.textContent = '✓';
        el.style.color = '#10b981';
    }
}


// =================================================================
// 6. CATALOG RENDERING & FOLDER NAVIGATION TREE
// =================================================================

function renderCatalog(catalog) {
    if (!catalog || !catalog.topics || catalog.topics.length === 0) {
        topicsTreeContainer.innerHTML = `
            <div style="text-align: center; padding: 30px; color: var(--text-muted);">
                📚 Lectures are being updated.<br>
                <small>Tap 🔄 Refresh to check for new uploads.</small>
            </div>
        `;
        return;
    }

    topicsTreeContainer.innerHTML = '';

    catalog.topics.forEach((topic, tIdx) => {
        const topicCard = document.createElement('div');
        topicCard.className = 'topic-accordion';

        // Header
        const header = document.createElement('div');
        header.className = 'topic-header';
        header.innerHTML = `
            <div class="topic-title-group">
                <span class="topic-icon">📚</span>
                <span class="topic-name">${escapeHtml(topic.title)}</span>
                ${topic.category ? `<span class="topic-category-badge" style="font-size: 0.72rem; background: rgba(99, 102, 241, 0.2); color: #a5b4fc; padding: 2px 7px; border-radius: 6px; font-weight: 600; border: 1px solid rgba(99, 102, 241, 0.3); margin-left: 4px;">${escapeHtml(topic.category)}</span>` : ''}
                <span class="topic-count-pill">${topic.lecture_count || 0} Lecs</span>
            </div>
            <span class="topic-toggle-icon">▼</span>
        `;
        header.addEventListener('click', () => {
            topicCard.classList.toggle('open');
        });

        // Content
        const content = document.createElement('div');
        content.className = 'topic-content';

        // Sections (Subfolder Chapters e.g. pinned messages 1, 2, 3, 4 - Unexpanded / Collapsed by default)
        topic.sections.forEach((section, sIdx) => {
            const secAccordion = document.createElement('div');
            secAccordion.className = 'section-accordion';

            const secHeader = document.createElement('div');
            secHeader.className = 'section-header';
            secHeader.innerHTML = `
                <div class="section-title-group">
                    <span>📁</span>
                    <span class="section-name">${escapeHtml(section.name)}</span>
                </div>
                <div class="section-right-group">
                    <span class="section-count-pill">${section.lectures?.length || 0} Lectures</span>
                    <span class="section-toggle-icon">▼</span>
                </div>
            `;

            // Toggle section accordion open / closed
            secHeader.addEventListener('click', (e) => {
                e.stopPropagation();
                secAccordion.classList.toggle('open');
            });

            const secContent = document.createElement('div');
            secContent.className = 'section-content';

            // Batches (Batch 1-5, Batch 6-10)
            const batchKeys = Object.keys(section.batches || {});
            batchKeys.forEach((bLabel, bIdx) => {
                const batchLectures = section.batches[bLabel];
                const batchKey = `${topic.title}_${section.name}_${bLabel}`;
                const isCompleted = userData.completed_batches?.includes(batchKey);

                const batchBox = document.createElement('div');
                batchBox.className = 'batch-card';

                const bHeader = document.createElement('div');
                bHeader.className = 'batch-header';
                bHeader.innerHTML = `
                    <span class="batch-label">🗂️ ${bLabel} (${batchLectures.length} Lectures)</span>
                    <div class="batch-actions">
                        ${isCompleted ? '<span class="batch-done-badge">Sent ✓</span>' : ''}
                        <button class="btn-send-batch" id="btn-batch-${tIdx}-${sIdx}-${bIdx}">
                            ${isCompleted ? 'Resend' : 'Send Batch'}
                        </button>
                    </div>
                `;

                // Add Jump feature if previous batches were done
                if (bIdx > 0 && !isCompleted) {
                    const jumpBtn = document.createElement('button');
                    jumpBtn.className = 'btn-jump';
                    jumpBtn.textContent = '⚡ Jump to this';
                    jumpBtn.addEventListener('click', () => {
                        startBatchForward(topic.title, section.name, bLabel, batchLectures);
                    });
                    bHeader.querySelector('.batch-actions').prepend(jumpBtn);
                }

                // Batch Send Button Action
                bHeader.querySelector('.btn-send-batch').addEventListener('click', () => {
                    startBatchForward(topic.title, section.name, bLabel, batchLectures);
                });

                batchBox.appendChild(bHeader);

                // Individual Lectures & Text Notes
                batchLectures.forEach(lec => {
                    const isSent = userData.sent_lectures?.includes(lec.id);
                    const lecEl = document.createElement('div');
                    lecEl.className = 'lecture-item';
                    const icon = lec.is_text ? '📝' : (lec.file_name?.toLowerCase().endsWith('.pdf') ? '📄' : '🎬');
                    const sizeText = lec.is_text ? 'Note' : `${lec.file_size_mb} MB`;

                    lecEl.innerHTML = `
                        <div class="lecture-left">
                            <span class="lecture-icon">${icon}</span>
                            <span class="lecture-title-text" title="${escapeHtml(lec.title)}">${escapeHtml(lec.title)}</span>
                        </div>
                        <div class="lecture-right">
                            <span class="lecture-size-pill">${sizeText}</span>
                            <span class="lecture-status-icon" id="lec-status-${lec.id}" style="color: ${isSent ? '#10b981' : '#64748b'};">
                                ${isSent ? '✓' : '○'}
                            </span>
                        </div>
                    `;
                    batchBox.appendChild(lecEl);
                });

                secContent.appendChild(batchBox);

                // Interleave 300x250 In-Feed Ad Banner between batches inside the chapter if configured
                if (window.adManager && typeof window.adManager.createInFeedAdCard === 'function') {
                    const adCard = window.adManager.createInFeedAdCard(`t${tIdx}-s${sIdx}-b${bIdx}`);
                    if (adCard) {
                        secContent.appendChild(adCard);
                    }
                }
            });

            secAccordion.appendChild(secHeader);
            secAccordion.appendChild(secContent);
            content.appendChild(secAccordion);
        });

        topicCard.appendChild(header);
        topicCard.appendChild(content);
        topicsTreeContainer.appendChild(topicCard);
    });
}

function handleSearchFilter(e) {
    const query = e.target.value.toLowerCase().trim();
    const topicCards = document.querySelectorAll('.topic-accordion');

    if (!query) {
        document.querySelectorAll('.lecture-item').forEach(el => el.style.display = 'flex');
        document.querySelectorAll('.batch-card').forEach(el => el.style.display = 'block');
        document.querySelectorAll('.section-accordion').forEach(el => {
            el.style.display = 'block';
            el.classList.remove('open');
        });
        topicCards.forEach(t => t.style.display = 'block');
        return;
    }

    topicCards.forEach(tCard => {
        let topicHasMatch = false;
        const topicTitle = tCard.querySelector('.topic-name')?.textContent.toLowerCase() || '';
        const topicMatches = topicTitle.includes(query);

        const secAccordions = tCard.querySelectorAll('.section-accordion');
        secAccordions.forEach(secAcc => {
            let secHasMatch = topicMatches;
            const secName = secAcc.querySelector('.section-name')?.textContent.toLowerCase() || '';
            const secMatches = secName.includes(query);

            const batchCards = secAcc.querySelectorAll('.batch-card');
            batchCards.forEach(bCard => {
                let batchHasMatch = topicMatches || secMatches;
                const batchLabel = bCard.querySelector('.batch-label')?.textContent.toLowerCase() || '';
                const batchMatches = batchLabel.includes(query);

                const items = bCard.querySelectorAll('.lecture-item');
                items.forEach(item => {
                    const title = item.querySelector('.lecture-title-text')?.textContent.toLowerCase() || '';
                    if (topicMatches || secMatches || batchMatches || title.includes(query)) {
                        item.style.display = 'flex';
                        batchHasMatch = true;
                    } else {
                        item.style.display = 'none';
                    }
                });

                bCard.style.display = batchHasMatch ? 'block' : 'none';
                if (batchHasMatch) secHasMatch = true;
            });

            secAcc.style.display = secHasMatch ? 'block' : 'none';
            if (secHasMatch) {
                topicHasMatch = true;
                secAcc.classList.add('open');
            }
        });

        tCard.style.display = topicHasMatch ? 'block' : 'none';
        if (topicHasMatch) {
            tCard.classList.add('open');
        }
    });
}


// =================================================================
// 7. SETTINGS MODAL & DESTINATION SAVING
// =================================================================

function openSettingsModal() {
    updateDestinationUI();
    if (destVerifyStatus) {
        destVerifyStatus.style.display = 'none';
        destVerifyStatus.className = 'verify-status-box';
    }
    settingsModal.classList.add('active');
    pushNavState('settings', closeSettingsModalInternal);
}

function closeSettingsModalInternal(shouldPopBrowserHistory = true) {
    settingsModal.classList.remove('active');
    popNavState('settings', shouldPopBrowserHistory);
}

function closeSettingsModal() {
    closeSettingsModalInternal(true);
}

async function handleVerifyDestination() {
    const rawDest = inputGroup.value.trim();
    const manualTopic = inputTopic.value.trim();

    if (!destVerifyStatus) return;

    if (!rawDest) {
        destVerifyStatus.className = 'verify-status-box success';
        destVerifyStatus.style.display = 'block';
        destVerifyStatus.innerHTML = '🤖 <strong>Bot PM (Default)</strong>: Unset destination sends all lectures directly to your private chat with the bot. No admin setup needed!';
        return;
    }

    destVerifyStatus.className = 'verify-status-box loading';
    destVerifyStatus.style.display = 'block';
    destVerifyStatus.innerHTML = '⏳ Checking destination connectivity and bot admin permissions...';

    try {
        const res = await fetch(`${API_BASE}/api/verify_destination`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                destination: rawDest,
                destination_input: rawDest,
                custom_group: rawDest,
                topic_id: manualTopic || null,
                custom_topic: manualTopic || null
            })
        });

        const data = await res.json();
        if (data.valid) {
            destVerifyStatus.className = 'verify-status-box success';
            if (data.is_pm) {
                destVerifyStatus.innerHTML = '🤖 <strong>Bot PM (Default)</strong>: All lectures will be delivered directly to your private chat with the bot.';
                userData.custom_group = null;
                userData.custom_topic = null;
                userData.custom_group_title = null;
            } else {
                destVerifyStatus.innerHTML = data.message || `✅ <strong>Verified & Saved!</strong> Forwarding set to <strong>${escapeHtml(data.chat_title || rawDest)}</strong>${data.topic_id ? ` (Topic ${data.topic_id})` : ''}!`;
                userData.custom_group = data.chat_id || rawDest;
                userData.custom_topic = data.topic_id || (manualTopic ? parseInt(manualTopic) : null);
                userData.custom_group_title = data.chat_title || null;
            }

            if (data.user_data) {
                userData = data.user_data;
            }

            if (data.topic_id) {
                inputTopic.value = data.topic_id;
            }

            // Immediately refresh the dashboard destination banner
            updateDestinationUI();

            // Background persist via save_settings endpoint to guarantee sync
            try {
                const saveRes = await fetch(`${API_BASE}/api/save_settings`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: USER_ID,
                        custom_group: userData.custom_group,
                        destination: userData.custom_group,
                        destination_input: rawDest,
                        custom_topic: userData.custom_topic,
                        topic_id: userData.custom_topic,
                        custom_bot_token: inputBotToken.value.trim() || null
                    })
                });
                if (saveRes.ok) {
                    const saveJson = await saveRes.json();
                    if (saveJson.data) {
                        userData = saveJson.data;
                        updateDestinationUI();
                    }
                }
            } catch (err) {
                console.warn('Auto-save error:', err);
            }
        } else {
            destVerifyStatus.className = 'verify-status-box error';
            destVerifyStatus.innerHTML = data.error || '❌ Could not verify destination permissions.';
        }
    } catch (e) {
        destVerifyStatus.className = 'verify-status-box error';
        destVerifyStatus.innerHTML = `❌ Network error connecting to verification API: ${e.message}`;
    }
}

async function handleSaveSettings(e) {
    e.preventDefault();
    const customGroup = inputGroup.value.trim() || null;
    const customTopic = inputTopic.value.trim() ? parseInt(inputTopic.value.trim()) : null;
    const customBotToken = inputBotToken.value.trim() || null;

    const saveBtn = document.getElementById('btn-save-settings');
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/save_settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                custom_group: customGroup,
                destination: customGroup,
                destination_input: customGroup,
                custom_topic: customTopic,
                topic_id: customTopic,
                custom_bot_token: customBotToken
            })
        });

        if (res.ok) {
            const data = await res.json();
            userData = data.data;
            updateDestinationUI();
            closeSettingsModal();
            const groupName = userData.custom_group_title || userData.custom_group;
            const destName = userData.custom_group ? `${groupName}${userData.custom_topic ? ` (Topic ${userData.custom_topic})` : ''}` : 'Bot PM (Default)';
            alert(`✅ Destination successfully set to: ${destName}`);
        } else {
            alert('Failed to save settings. Please try again.');
        }
    } catch (err) {
        console.error(err);
        alert('Network error saving settings.');
    } finally {
        saveBtn.textContent = 'Save Destination';
        saveBtn.disabled = false;
    }
}


// =================================================================
// 8. UTILITIES & DEMO CATALOG FALLBACK
// =================================================================

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function showMockCatalog() {
    // Elegant fallback catalog when running in development without Telegram backend connection
    const mock = {
        topics: [
            {
                title: "Biology (Class 11 & 12)",
                lecture_count: 10,
                sections: [
                    {
                        name: "Living World (Main Lectures)",
                        batches: {
                            "Batch 1-5": [
                                { id: "1_101", message_id: 101, title: "Lec 01 - What is Living & Characteristics", file_size_mb: 245.5 },
                                { id: "1_102", message_id: 102, title: "Lec 02 - Diversity in Living World & Taxon", file_size_mb: 310.2 },
                                { id: "1_103", message_id: 103, title: "Lec 03 - Taxonomic Categories & Hierarchy", file_size_mb: 198.8 },
                                { id: "1_104", message_id: 104, title: "Lec 04 - Taxonomical Aids & Herbarium", file_size_mb: 260.0 },
                                { id: "1_105", message_id: 105, title: "Lec 05 - Chapter Summary & One Shot", file_size_mb: 412.4 }
                            ],
                            "Batch 6-10": [
                                { id: "1_106", message_id: 106, title: "Lec 06 - NCERT Line by Line Reading 01", file_size_mb: 180.5 },
                                { id: "1_107", message_id: 107, title: "Lec 07 - NCERT Line by Line Reading 02", file_size_mb: 215.1 },
                                { id: "1_108", message_id: 108, title: "Lec 08 - Top 100 NEET Questions Practice", file_size_mb: 330.0 },
                                { id: "1_109", message_id: 109, title: "Lec 09 - PYQs Discussion (2015-2025)", file_size_mb: 290.4 },
                                { id: "1_110", message_id: 110, title: "Lec 10 - Final Mindmap & Formula Sheet", file_size_mb: 150.2 }
                            ]
                        }
                    }
                ]
            }
        ]
    };
    appCatalog = mock;
    renderCatalog(mock);
}


// =================================================================
// 9. ADMIN COMMAND CENTER CONTROLLER (ADMIN_ID ONLY)
// =================================================================

async function checkAdminStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/admin/info?user_id=${USER_ID}`);
        if (res.ok) {
            const data = await res.json();
            if (data.is_admin) {
                isAdmin = true;
                adminCachedData = data;
                if (btnAdminPanel) {
                    btnAdminPanel.style.display = 'inline-flex';
                }
                if (adminIdBadge) {
                    adminIdBadge.textContent = `Admin ID: ${data.admin_id || USER_ID}`;
                }
            }
        }
    } catch (e) {
        // Normal students receive 403 or network fallback silently
        console.debug('Admin check note:', e);
    }
}

function openAdminModal() {
    if (!isAdmin || !adminModal) return;
    adminModal.classList.add('active');
    loadAdminData();
    pushNavState('admin', closeAdminModalInternal);
}

function closeAdminModalInternal(shouldPopBrowserHistory = true) {
    if (adminModal) adminModal.classList.remove('active');
    popNavState('admin', shouldPopBrowserHistory);
}

function closeAdminModal() {
    closeAdminModalInternal(true);
}

async function loadAdminData() {
    if (!isAdmin) return;
    try {
        const res = await fetch(`${API_BASE}/api/admin/info?user_id=${USER_ID}`);
        if (res.ok) {
            const data = await res.json();
            adminCachedData = data;
            renderAdminStats(data);
            renderAdminTopicsList(data.topics || [], data.hidden_topics || []);
        }
    } catch (e) {
        console.error('Failed to load admin metrics:', e);
    }
}

function renderAdminStats(data) {
    if (adminStatStudents) adminStatStudents.textContent = data.total_students || 0;
    if (adminStatLectures) adminStatLectures.textContent = data.total_lectures || 0;
    if (adminStatTopics) {
        const visibleCount = (data.topics || []).filter(t => !t.is_hidden).length;
        adminStatTopics.textContent = `${visibleCount}/${(data.topics || []).length}`;
    }
    if (adminStatQueue) {
        const backlog = data.queue?.active_count || 0;
        adminStatQueue.textContent = backlog > 0 ? `${backlog} busy` : '0 idle';
    }
    if (adminLastScanned) {
        if (data.last_scanned) {
            const date = new Date(data.last_scanned);
            adminLastScanned.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' (' + date.toLocaleDateString() + ')';
        } else {
            adminLastScanned.textContent = 'Auto-Indexed';
        }
    }
}

function renderAdminTopicsList(topics, hiddenTopics) {
    if (!adminTopicsList) return;
    adminTopicsList.innerHTML = '';

    if (!topics || topics.length === 0) {
        adminTopicsList.innerHTML = '<div class="admin-loading-row">No topics discovered in forum yet.</div>';
        return;
    }

    const filterVal = (adminTopicSearch?.value || '').toLowerCase().trim();

    topics.forEach((topic) => {
        const title = topic.title || 'Untitled Topic';
        const category = topic.category || 'General';
        const threadId = topic.thread_id || 1;
        const lectureCount = topic.lecture_count || 0;
        const topicKey = topic.thread_id || topic.title;

        if (filterVal) {
            const match = title.toLowerCase().includes(filterVal) ||
                          category.toLowerCase().includes(filterVal) ||
                          String(threadId).includes(filterVal);
            if (!match) return;
        }

        const isHidden = topic.is_hidden || (hiddenTopics && (
            hiddenTopics.includes(String(threadId)) ||
            hiddenTopics.includes(title) ||
            hiddenTopics.includes(category)
        ));

        const row = document.createElement('div');
        row.className = `admin-topic-row ${isHidden ? 'hidden-topic' : ''}`;
        row.id = `admin-topic-row-${threadId}`;

        row.innerHTML = `
            <div class="admin-topic-meta">
                <div class="admin-topic-name">${escapeHtml(title)}</div>
                <div class="admin-topic-sub">
                    <span class="topic-category-badge">${escapeHtml(category)}</span>
                    <span>• ${lectureCount} lectures</span>
                    <span>• Thread ID: ${threadId}</span>
                    <span class="status-badge" style="font-weight:700; color: ${isHidden ? '#ef4444' : '#10b981'}">
                        ${isHidden ? '🙈 Hidden' : '👁️ Visible'}
                    </span>
                </div>
            </div>
            <label class="admin-switch">
                <input type="checkbox" class="topic-visibility-toggle" data-topic-key="${escapeHtml(String(topicKey))}" ${isHidden ? '' : 'checked'}>
                <span class="admin-slider"></span>
            </label>
        `;

        const checkbox = row.querySelector('.topic-visibility-toggle');
        checkbox.addEventListener('change', async (e) => {
            const checked = e.target.checked;
            await toggleTopicVisibility(topicKey, checked, row);
        });

        adminTopicsList.appendChild(row);
    });
}

async function toggleTopicVisibility(topicKey, isNowVisible, rowEl) {
    try {
        const statusSpan = rowEl.querySelector('.status-badge');
        if (statusSpan) statusSpan.textContent = 'Updating...';

        const res = await fetch(`${API_BASE}/api/admin/toggle_topic`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                topic_key: topicKey
            })
        });

        if (res.ok) {
            const data = await res.json();
            const isHidden = !isNowVisible;
            if (rowEl) {
                rowEl.classList.toggle('hidden-topic', isHidden);
                if (statusSpan) {
                    statusSpan.textContent = isHidden ? '🙈 Hidden' : '👁️ Visible';
                    statusSpan.style.color = isHidden ? '#ef4444' : '#10b981';
                }
            }
            if (data.topics) {
                renderAdminStats({
                    ...adminCachedData,
                    topics: data.topics,
                    hidden_topics: data.hidden_topics
                });
            }
            // Refresh catalog outside modal
            await loadCatalog();
        } else {
            alert('Failed to update topic visibility. Please try again.');
        }
    } catch (e) {
        console.error('Error toggling topic:', e);
        alert('Network error while toggling topic.');
    }
}

async function handleAdminRescan() {
    if (!btnAdminRescanTrigger) return;
    const originalText = btnAdminRescanTrigger.textContent;
    btnAdminRescanTrigger.disabled = true;
    btnAdminRescanTrigger.textContent = '🔄 Re-scanning Forum... (Please wait)';

    try {
        const res = await fetch(`${API_BASE}/api/admin/rescan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: USER_ID })
        });

        if (res.ok) {
            btnAdminRescanTrigger.textContent = '✅ Re-Scan Complete!';
            await loadAdminData();
            await loadCatalog();
            setTimeout(() => {
                btnAdminRescanTrigger.textContent = originalText;
                btnAdminRescanTrigger.disabled = false;
            }, 2500);
        } else {
            btnAdminRescanTrigger.textContent = '❌ Failed';
            setTimeout(() => {
                btnAdminRescanTrigger.textContent = originalText;
                btnAdminRescanTrigger.disabled = false;
            }, 2000);
        }
    } catch (e) {
        console.error(e);
        btnAdminRescanTrigger.textContent = '⚠️ Network Error';
        setTimeout(() => {
            btnAdminRescanTrigger.textContent = originalText;
            btnAdminRescanTrigger.disabled = false;
        }, 2000);
    }
}

async function handleCurateSubmit(e) {
    e.preventDefault();
    if (!btnCurateSubmit) return;

    const category = curateCategory.value.trim();
    const subject = curateSubject.value.trim();
    const chapter = curateChapter.value.trim();
    const startId = parseInt(curateStartId.value);
    const endId = parseInt(curateEndId.value);
    const sourceGroup = curateSourceGroup ? curateSourceGroup.value.trim() : '';

    if (!category || !subject || !chapter || isNaN(startId) || isNaN(endId)) {
        alert('Please fill in all required fields.');
        return;
    }

    if (startId > endId) {
        alert('Start Message ID must be less than or equal to End Message ID.');
        return;
    }

    const originalBtnText = btnCurateSubmit.textContent;
    btnCurateSubmit.disabled = true;
    btnCurateSubmit.textContent = '⏳ Saving & Indexing Range...';

    try {
        const res = await fetch(`${API_BASE}/api/admin/add_chapter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                category,
                subject,
                chapter,
                start_id: startId,
                end_id: endId,
                source_group: sourceGroup || null
            })
        });

        if (res.ok) {
            btnCurateSubmit.textContent = '✅ Chapter Indexed!';
            adminCurateForm.reset();
            await loadAdminData();
            await loadCatalog();
            alert(`🎉 Success! Chapter '${chapter}' (${startId}-${endId}) added to ${subject} [${category}].`);
            setTimeout(() => {
                btnCurateSubmit.textContent = originalBtnText;
                btnCurateSubmit.disabled = false;
            }, 2000);
        } else {
            alert('Could not add chapter. Check server logs.');
            btnCurateSubmit.textContent = originalBtnText;
            btnCurateSubmit.disabled = false;
        }
    } catch (err) {
        console.error(err);
        alert('Network error while saving chapter.');
        btnCurateSubmit.textContent = originalBtnText;
        btnCurateSubmit.disabled = false;
    }
}
