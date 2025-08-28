/**
 * API Key Loader
 * Loads Gemini API key from server-side storage and manages it in localStorage
 */

class APIKeyLoader {
    constructor() {
        this.apiKeyPath = '~/.gemini_api_key';
        this.localStorageKey = 'gemini-api-key';
        this.initialized = false;
    }

    /**
     * Initialize API key loading on page load
     */
    async initialize() {
        if (this.initialized) return;
        
        try {
            // Check if key exists in localStorage
            let apiKey = localStorage.getItem(this.localStorageKey);
            
            // If no key in localStorage, try to load from server
            if (!apiKey || apiKey === 'null' || apiKey === 'undefined' || apiKey === '') {
                apiKey = await this.loadFromServer();
                if (apiKey && apiKey !== 'YOUR_API_KEY_HERE') {
                    this.saveToLocalStorage(apiKey);
                    console.log('✓ Gemini API key loaded from server');
                }
            } else {
                console.log('✓ Gemini API key found in localStorage');
            }
            
            // Verify the key is valid
            if (!apiKey || apiKey === 'YOUR_API_KEY_HERE') {
                console.warn('⚠️ No valid Gemini API key found. Please configure it in the settings.');
                this.promptForApiKey();
            }
            
            this.initialized = true;
        } catch (error) {
            console.error('Error initializing API key:', error);
        }
    }

    /**
     * Load API key from server-side file
     */
    async loadFromServer() {
        try {
            const response = await fetch('/api/load-api-key', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                return data.apiKey;
            }
        } catch (error) {
            console.error('Error loading API key from server:', error);
        }
        return null;
    }

    /**
     * Save API key to localStorage
     */
    saveToLocalStorage(apiKey) {
        if (apiKey && apiKey !== 'YOUR_API_KEY_HERE') {
            localStorage.setItem(this.localStorageKey, apiKey);
        }
    }

    /**
     * Save API key to both localStorage and server
     */
    async saveApiKey(apiKey) {
        // Save to localStorage
        this.saveToLocalStorage(apiKey);
        
        // Save to server
        try {
            const response = await fetch('/api/save-api-key', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ apiKey })
            });

            if (response.ok) {
                console.log('✓ API key saved to server');
                return true;
            }
        } catch (error) {
            console.error('Error saving API key to server:', error);
        }
        return false;
    }

    /**
     * Get the current API key
     */
    getApiKey() {
        return localStorage.getItem(this.localStorageKey);
    }

    /**
     * Prompt user to enter API key if not configured
     */
    promptForApiKey() {
        // Check if settings modal exists
        const settingsBtn = document.querySelector('[onclick*="openSettings"]');
        if (settingsBtn) {
            // Add visual indicator
            settingsBtn.style.animation = 'pulse 2s infinite';
            settingsBtn.title = 'Please configure your Gemini API key';
            
            // Add CSS animation if not exists
            if (!document.querySelector('#api-key-pulse-animation')) {
                const style = document.createElement('style');
                style.id = 'api-key-pulse-animation';
                style.textContent = `
                    @keyframes pulse {
                        0% { opacity: 1; }
                        50% { opacity: 0.5; background-color: #ffeb3b; }
                        100% { opacity: 1; }
                    }
                `;
                document.head.appendChild(style);
            }
        }
    }

    /**
     * Clear API key from storage
     */
    clearApiKey() {
        localStorage.removeItem(this.localStorageKey);
        console.log('API key cleared from localStorage');
    }
}

// Create global instance
window.apiKeyLoader = new APIKeyLoader();

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.apiKeyLoader.initialize();
    });
} else {
    window.apiKeyLoader.initialize();
}