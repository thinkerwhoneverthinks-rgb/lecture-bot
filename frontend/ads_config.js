/**
 * Adsterra & Monetization Configuration
 * Live Monetization Units Configured with User Credentials
 */

const ADS_CONFIG = {
    // Master switch to enable/disable ads across the Mini App
    enabled: true,

    // Adsterra Sticky Footer 320x50 Banner (permanent outside the content)
    sticky_footer_320x50: {
        enabled: true,
        key: "47e4164fcf0e625d122335dd71c6e9f8",
        script_url: "https://bauval.org/22/47e4164fcf0e625d122335dd71c6e9f8",
        container_id: "sticky-footer-ad-container",
        width: 320,
        height: 50,
        refresh_interval_sec: 45
    },

    // Adsterra 300x250 In-Feed Banners (interleaved between batch cards)
    infeed_300x250: {
        enabled: true,
        key: "71582c8c44b686f2f87262a395bfd6e5",
        script_url: "https://bauval.org/22/71582c8c44b686f2f87262a395bfd6e5",
        width: 300,
        height: 250,
        refresh_interval_sec: 35
    },

    // Adsterra Social Bar (In-page push notification widget - High CPM)
    social_bar: {
        enabled: true,
        script_url: "https://bauval.org/14/c722572355e692dadb25a8321535b206"
    }
};

/**
 * Ad Manager Helper to load and cycle Adsterra ads
 */
class AdManager {
    constructor(config) {
        this.config = config;
        this.refreshTimer = null;
        this.infeedSlots = [];
        this.totalRefreshes = 0;
    }

    init() {
        if (!this.config.enabled) return;

        // 1. Inject Social Bar Script if not already loaded in head
        if (this.config.social_bar?.enabled && this.config.social_bar?.script_url) {
            this.loadSocialBar(this.config.social_bar.script_url);
        }

        // 2. Render Sticky Footer 320x50 Banner
        this.renderStickyFooter();

        // 3. Start auto-rotation timer (every 35s safe interval)
        this.startAutoRefreshCycle();
    }

    loadSocialBar(url) {
        if (document.getElementById('adsterra-socialbar-script')) return;
        try {
            const script = document.createElement('script');
            script.id = 'adsterra-socialbar-script';
            script.setAttribute('data-cfasync', 'false');
            script.src = url;
            script.async = true;
            document.head.appendChild(script);
            console.log('[AdManager] Injected Social Bar script');
        } catch (e) {
            console.warn('[AdManager] Error loading Social Bar:', e);
        }
    }

    buildIframeDoc(key, scriptUrl, width, height) {
        const cacheBuster = Date.now();
        return `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    html, body {
                        margin: 0;
                        padding: 0;
                        width: ${width}px;
                        height: ${height}px;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        background: transparent;
                        overflow: hidden;
                    }
                </style>
            </head>
            <body>
                <script type="text/javascript">
                    atOptions = {
                        'key' : '${key}',
                        'format' : 'iframe',
                        'height' : ${height},
                        'width' : ${width},
                        'params' : { 'cb': '${cacheBuster}' }
                    };
                </script>
                <script type="text/javascript" src="${scriptUrl}"></script>
            </body>
            </html>
        `;
    }

    renderStickyFooter() {
        if (!this.config.enabled || !this.config.sticky_footer_320x50?.enabled) return;

        const container = document.getElementById(this.config.sticky_footer_320x50.container_id);
        if (!container) return;

        const { key, script_url, width, height } = this.config.sticky_footer_320x50;

        container.innerHTML = '';
        const iframe = document.createElement('iframe');
        iframe.width = width;
        iframe.height = height;
        iframe.frameBorder = '0';
        iframe.scrolling = 'no';
        iframe.style.border = 'none';
        iframe.style.overflow = 'hidden';
        iframe.style.maxWidth = '100%';
        iframe.srcdoc = this.buildIframeDoc(key, script_url, width, height);

        container.appendChild(iframe);
        console.log('[AdManager] Rendered Sticky Footer 320x50 Banner');
    }

    createInFeedAdCard(slotId) {
        if (!this.config.enabled || !this.config.infeed_300x250?.enabled) return null;

        const { key, script_url, width, height } = this.config.infeed_300x250;

        const card = document.createElement('div');
        card.className = 'infeed-ad-card';
        card.id = `ad-slot-${slotId}`;

        const label = document.createElement('div');
        label.className = 'infeed-ad-label';
        label.innerHTML = '<span>📢</span><span>Sponsored</span><span>📢</span>';
        card.appendChild(label);

        const iframe = document.createElement('iframe');
        iframe.className = 'infeed-ad-iframe';
        iframe.width = width;
        iframe.height = height;
        iframe.frameBorder = '0';
        iframe.scrolling = 'no';
        iframe.style.border = 'none';
        iframe.style.overflow = 'hidden';
        iframe.style.borderRadius = '8px';
        iframe.style.maxWidth = '100%';
        iframe.srcdoc = this.buildIframeDoc(key, script_url, width, height);

        card.appendChild(iframe);

        // Register for auto-refresh
        this.infeedSlots.push({ id: slotId, iframe: iframe });

        return card;
    }

    startAutoRefreshCycle() {
        this.stopAutoRefreshCycle();

        const intervalSec = this.config.infeed_300x250.refresh_interval_sec || 35;
        this.refreshTimer = setInterval(() => {
            this.cycleVisibleBanners();
        }, intervalSec * 1000);
    }

    stopAutoRefreshCycle() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    cycleVisibleBanners() {
        if (!this.config.enabled) return;

        // Clean up disconnected iframes
        this.infeedSlots = this.infeedSlots.filter(s => s.iframe && document.body.contains(s.iframe));

        // Refresh visible in-feed ads (inside open accordions)
        const { key, script_url, width, height } = this.config.infeed_300x250;
        let refreshedCount = 0;

        this.infeedSlots.forEach(s => {
            // Check if element is visible on screen
            if (s.iframe.offsetParent !== null) {
                s.iframe.srcdoc = this.buildIframeDoc(key, script_url, width, height);
                refreshedCount++;
            }
        });

        // Also refresh the sticky footer banner
        this.renderStickyFooter();

        this.totalRefreshes++;
        if (refreshedCount > 0) {
            console.log(`[AdManager] Refreshed ${refreshedCount} visible in-feed banner(s) (Cycle #${this.totalRefreshes})`);
        }
    }

    startBatchRefreshCycle() {
        // Immediate cycle when user starts forwarding a batch
        this.cycleVisibleBanners();
    }

    stopBatchRefreshCycle() {
        // Keeps standard background auto-refresh running
    }
}

// Global Ad Manager instance
window.adManager = new AdManager(ADS_CONFIG);
