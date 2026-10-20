/**
 * Adsterra & Monetization Configuration
 * Live Monetization Units Configured with User Credentials
 */

const ADS_CONFIG = {
    // Master switch to enable/disable ads across the Mini App
    enabled: true,

    // Adsterra 300x250 Banner settings
    banner_300x250: {
        enabled: true,
        key: "71582c8c44b686f2f87262a395bfd6e5",
        script_url: "https://bauval.org/22/71582c8c44b686f2f87262a395bfd6e5",
        container_id: "adsterra-banner-container",
        width: 300,
        height: 250,
        // Auto-refresh interval in seconds during batch processing to register new impressions
        refresh_interval_sec: 30
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
        this.adViewCount = 0;
    }

    init() {
        if (!this.config.enabled) return;

        // 1. Inject Social Bar Script into page head
        if (this.config.social_bar?.enabled && this.config.social_bar?.script_url) {
            this.loadSocialBar(this.config.social_bar.script_url);
        }

        // 2. Initial 300x250 Banner Render
        this.renderBanner();
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

    renderBanner() {
        if (!this.config.enabled || !this.config.banner_300x250?.enabled) return;

        const container = document.getElementById(this.config.banner_300x250.container_id);
        if (!container) return;

        const key = this.config.banner_300x250.key;
        const scriptUrl = this.config.banner_300x250.script_url;
        const width = this.config.banner_300x250.width || 300;
        const height = this.config.banner_300x250.height || 250;

        // Clear existing ad container content safely
        container.innerHTML = '';

        // Render via an isolated iframe to prevent script interference and allow clean refreshing
        const iframe = document.createElement('iframe');
        iframe.width = width;
        iframe.height = height;
        iframe.frameBorder = '0';
        iframe.scrolling = 'no';
        iframe.style.border = 'none';
        iframe.style.overflow = 'hidden';
        iframe.style.borderRadius = '8px';
        iframe.style.maxWidth = '100%';

        const iframeHtml = `
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
                        'params' : {}
                    };
                </script>
                <script type="text/javascript" src="${scriptUrl}"></script>
            </body>
            </html>
        `;

        iframe.srcdoc = iframeHtml;
        container.appendChild(iframe);

        this.adViewCount++;
        console.log(`[AdManager] Rendered 300x250 banner view #${this.adViewCount}`);
    }

    startBatchRefreshCycle() {
        if (!this.config.enabled || !this.config.banner_300x250?.enabled) return;
        this.stopBatchRefreshCycle();

        // Refresh banner on batch start to capture student impression
        this.renderBanner();

        // Cycle ad banner periodically while student waits for batch upload
        const intervalMs = (this.config.banner_300x250.refresh_interval_sec || 30) * 1000;
        this.refreshTimer = setInterval(() => {
            console.log('[AdManager] Refreshing banner impression cycle...');
            this.renderBanner();
        }, intervalMs);
    }

    stopBatchRefreshCycle() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }
}

// Global Ad Manager instance
window.adManager = new AdManager(ADS_CONFIG);
