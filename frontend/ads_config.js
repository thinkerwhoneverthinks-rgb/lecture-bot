/**
 * Adsterra & Monetization Configuration
 * Easily configure your Adsterra ad scripts and auto-refresh intervals here.
 */

const ADS_CONFIG = {
    // Master switch to enable/disable ads across the Mini App
    enabled: true,

    // Adsterra 300x250 Banner settings
    banner_300x250: {
        enabled: true,
        // Replace with your Adsterra direct banner script URL or key
        // Example: "//www.highperformanceformat.com/YOUR_KEY_HERE/invoke.js"
        script_url: "//www.highperformanceformat.com/example_banner_key/invoke.js",
        container_id: "adsterra-banner-container",
        // Auto-refresh interval in seconds during batch processing to register new impressions
        refresh_interval_sec: 25
    },

    // Adsterra Social Bar (In-page push notification widget - High CPM)
    social_bar: {
        enabled: true,
        // Replace with your Adsterra Social Bar script URL
        // Example: "//pl12345678.effectivegate.com/YOUR_SOCIAL_BAR_KEY.js"
        script_url: "//pl12345678.effectivegate.com/example_socialbar_key.js"
    },

    // Smart Direct Link (Optional bonus link / sponsored action)
    direct_link: {
        enabled: false,
        url: "https://www.profitablecpmrate.com/your_direct_link"
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

        // 1. Load Social Bar if configured
        if (this.config.social_bar.enabled && this.config.social_bar.script_url) {
            this.loadScript(this.config.social_bar.script_url, 'adsterra-socialbar-script');
        }

        // 2. Initial Banner Load
        this.renderBanner();
    }

    renderBanner() {
        if (!this.config.enabled || !this.config.banner_300x250.enabled) return;

        const container = document.getElementById(this.config.banner_300x250.container_id);
        if (!container) return;

        // Clear existing ad container content safely
        container.innerHTML = '';

        // Create fresh ad wrapper iframe or script element
        const adWrapper = document.createElement('div');
        adWrapper.className = 'ad-rendered-slot';

        // Check if demo/placeholder mode vs live script
        if (this.config.banner_300x250.script_url.includes('example_banner_key')) {
            // Friendly preview placeholder showing where Adsterra renders
            adWrapper.innerHTML = `
                <div class="ad-preview-box">
                    <div class="ad-preview-badge">📢 SPONSORED AD SPOT (300x250)</div>
                    <div class="ad-preview-text">Adsterra banner renders here live!</div>
                    <small>Auto-refreshes every ${this.config.banner_300x250.refresh_interval_sec}s for maximum views</small>
                </div>
            `;
        } else {
            // Live Adsterra Script Injection
            const script = document.createElement('script');
            script.type = 'text/javascript';
            script.src = this.config.banner_300x250.script_url;
            script.async = true;
            adWrapper.appendChild(script);
        }

        container.appendChild(adWrapper);
        this.adViewCount++;
        console.log(`[AdManager] Rendered ad view #${this.adViewCount}`);
    }

    startBatchRefreshCycle() {
        if (!this.config.enabled || !this.config.banner_300x250.enabled) return;
        this.stopBatchRefreshCycle();

        // Refresh ad on batch start
        this.renderBanner();

        // Cycle ad every N seconds to capture fresh impressions while user waits for batch
        const intervalMs = (this.config.banner_300x250.refresh_interval_sec || 25) * 1000;
        this.refreshTimer = setInterval(() => {
            console.log('[AdManager] Refreshing ad for new impression view...');
            this.renderBanner();
        }, intervalMs);
    }

    stopBatchRefreshCycle() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    loadScript(url, id) {
        if (document.getElementById(id)) return;
        const script = document.createElement('script');
        script.id = id;
        script.type = 'text/javascript';
        script.src = url;
        script.async = true;
        document.body.appendChild(script);
    }
}

// Global Ad Manager instance
window.adManager = new AdManager(ADS_CONFIG);
