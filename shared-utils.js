/**
 * Shared Utilities for PDF Schedule Extractor
 * Common JavaScript functions used across multiple HTML files
 */

(function() {
    'use strict';

    /**
     * Modal Management Utilities
     */
    window.ModalUtils = {
        /**
         * Open a modal by ID
         * @param {string} modalId - The ID of the modal to open
         * @param {Object} options - Optional configuration
         */
        open(modalId, options = {}) {
            const modal = document.getElementById(modalId);
            if (!modal) {
                console.warn(`Modal with ID '${modalId}' not found`);
                return false;
            }

            // Add show class for CSS transitions
            modal.classList.add('show');
            modal.style.display = 'flex';

            // Focus management
            if (options.focusElement) {
                const focusTarget = modal.querySelector(options.focusElement);
                if (focusTarget) {
                    setTimeout(() => focusTarget.focus(), 100);
                }
            }

            // Close on background click
            if (options.closeOnBackdrop !== false) {
                modal.addEventListener('click', this._handleBackdropClick.bind(this, modalId));
            }

            // Close on escape key
            if (options.closeOnEscape !== false) {
                document.addEventListener('keydown', this._handleEscapeKey.bind(this, modalId));
            }

            return true;
        },

        /**
         * Close a modal by ID
         * @param {string} modalId - The ID of the modal to close
         */
        close(modalId) {
            const modal = document.getElementById(modalId);
            if (!modal) {
                return false;
            }

            modal.classList.remove('show');
            modal.style.display = 'none';

            // Remove event listeners
            modal.removeEventListener('click', this._handleBackdropClick);
            document.removeEventListener('keydown', this._handleEscapeKey);

            return true;
        },

        /**
         * Close all open modals
         */
        closeAll() {
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(modal => {
                this.close(modal.id);
            });
        },

        /**
         * Setup modal handlers for all modals on the page
         */
        setupModalHandlers() {
            // Handle close buttons
            document.querySelectorAll('.modal-close, .close-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const modal = btn.closest('.modal');
                    if (modal) {
                        this.close(modal.id);
                    }
                });
            });

            // Handle cancel buttons
            document.querySelectorAll('[id$="-cancel"]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const modal = btn.closest('.modal');
                    if (modal) {
                        this.close(modal.id);
                    }
                });
            });
        },

        /**
         * Handle backdrop clicks
         */
        _handleBackdropClick(modalId, e) {
            if (e.target === e.currentTarget) {
                this.close(modalId);
            }
        },

        /**
         * Handle escape key
         */
        _handleEscapeKey(modalId, e) {
            if (e.key === 'Escape') {
                this.close(modalId);
            }
        }
    };

    /**
     * API Configuration and Utilities
     */
    window.ApiUtils = {
        // Will be initialized from config
        _config: null,

        /**
         * Initialize API utilities with configuration
         * @param {Object} config - Configuration object
         */
        init(config) {
            this._config = config;
        },

        /**
         * Get the server URL
         * @returns {string} Server URL
         */
        getServerUrl() {
            const port = this._config?.apiSettings?.serverPort || 5000;
            return `http://${window.location.hostname}:${port}`;
        },

        /**
         * Build full API URL for an endpoint
         * @param {string} endpoint - Endpoint key or path
         * @returns {string} Full API URL
         */
        buildApiUrl(endpoint) {
            const baseUrl = this.getServerUrl();
            
            // Check if endpoint is a key in config
            if (this._config?.apiSettings?.endpoints?.[endpoint]) {
                return `${baseUrl}${this._config.apiSettings.endpoints[endpoint]}`;
            }
            
            // If not in config, treat as direct path
            if (!endpoint.startsWith('/')) {
                endpoint = '/' + endpoint;
            }
            
            return `${baseUrl}${endpoint}`;
        },

        /**
         * Fetch with timeout support
         * @param {string} url - URL to fetch
         * @param {Object} options - Fetch options
         * @param {number} timeout - Timeout in milliseconds
         * @returns {Promise} Fetch promise with timeout
         */
        async fetchWithTimeout(url, options = {}, timeout = null) {
            timeout = timeout || this._config?.apiSettings?.timeout || 3000;
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);
            
            try {
                const response = await fetch(url, {
                    ...options,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                return response;
            } catch (error) {
                clearTimeout(timeoutId);
                if (error.name === 'AbortError') {
                    throw new Error('Request timeout');
                }
                throw error;
            }
        },

        /**
         * Check server health
         * @returns {Promise<boolean>} Server health status
         */
        async checkServerHealth() {
            try {
                const response = await this.fetchWithTimeout(this.buildApiUrl('health'));
                return response.ok;
            } catch (error) {
                return false;
            }
        }
    };

    /**
     * File Operation Utilities
     */
    window.FileUtils = {
        /**
         * Download a file from URL
         * @param {string} url - File URL
         * @param {string} filename - Suggested filename
         */
        downloadFile(url, filename) {
            const link = document.createElement('a');
            link.href = url;
            link.download = filename || 'download';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        },

        /**
         * Download a blob as file
         * @param {Blob} blob - Blob data
         * @param {string} filename - Filename
         */
        downloadBlob(blob, filename) {
            const url = URL.createObjectURL(blob);
            this.downloadFile(url, filename);
            setTimeout(() => URL.revokeObjectURL(url), 100);
        },

        /**
         * Create object URL from data
         * @param {Blob|File} data - Data to create URL for
         * @returns {string} Object URL
         */
        createObjectUrl(data) {
            return URL.createObjectURL(data);
        },

        /**
         * Revoke object URL
         * @param {string} url - URL to revoke
         */
        revokeObjectUrl(url) {
            URL.revokeObjectURL(url);
        },

        /**
         * Read file as text
         * @param {File} file - File to read
         * @returns {Promise<string>} File content as text
         */
        readFileAsText(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = e => resolve(e.target.result);
                reader.onerror = e => reject(e);
                reader.readAsText(file);
            });
        },

        /**
         * Read file as data URL
         * @param {File} file - File to read
         * @returns {Promise<string>} File content as data URL
         */
        readFileAsDataURL(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = e => resolve(e.target.result);
                reader.onerror = e => reject(e);
                reader.readAsDataURL(file);
            });
        }
    };

    /**
     * Format Utilities
     */
    window.FormatUtils = {
        /**
         * Format date to readable string
         * @param {Date|string} date - Date to format
         * @param {Object} options - Formatting options
         * @returns {string} Formatted date
         */
        formatDate(date, options = {}) {
            if (typeof date === 'string') {
                date = new Date(date);
            }
            
            if (!(date instanceof Date) || isNaN(date)) {
                return 'Invalid Date';
            }

            const defaultOptions = {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            };

            return date.toLocaleString('en-US', { ...defaultOptions, ...options });
        },

        /**
         * Format file size to human readable
         * @param {number} bytes - File size in bytes
         * @param {number} decimals - Number of decimal places
         * @returns {string} Formatted file size
         */
        formatFileSize(bytes, decimals = 2) {
            if (bytes === 0) return '0 Bytes';
            
            const k = 1024;
            const dm = decimals < 0 ? 0 : decimals;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            
            return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
        },

        /**
         * Truncate text to specified length
         * @param {string} text - Text to truncate
         * @param {number} length - Maximum length
         * @param {string} suffix - Suffix to add (default: '...')
         * @returns {string} Truncated text
         */
        truncateText(text, length, suffix = '...') {
            if (!text || text.length <= length) {
                return text;
            }
            
            return text.substring(0, length - suffix.length) + suffix;
        },

        /**
         * Capitalize first letter of each word
         * @param {string} str - String to capitalize
         * @returns {string} Capitalized string
         */
        capitalizeWords(str) {
            if (!str) return str;
            
            return str.replace(/\w\S*/g, (txt) => 
                txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase()
            );
        },

        /**
         * Generate unique ID
         * @param {string} prefix - Optional prefix
         * @returns {string} Unique ID
         */
        generateId(prefix = 'id') {
            const timestamp = Date.now().toString(36);
            const random = Math.random().toString(36).substr(2, 5);
            return `${prefix}_${timestamp}_${random}`;
        }
    };

    /**
     * Equipment Type Utilities
     */
    window.EquipmentUtils = {
        /**
         * Get equipment type label
         * @param {string} value - Equipment type value
         * @param {Array} equipmentTypes - Equipment types array
         * @returns {string} Equipment type label
         */
        getLabel(value, equipmentTypes) {
            if (!equipmentTypes || !Array.isArray(equipmentTypes)) {
                return value;
            }
            
            const type = equipmentTypes.find(t => t.value === value);
            return type ? type.label : value;
        },

        /**
         * Get equipment type icon
         * @param {string} value - Equipment type value
         * @returns {string} Icon class or symbol
         */
        getIcon(value) {
            const icons = {
                'FANS': '🌀',
                'VAV': '🎛️',
                'RTU': '🏠',
                'AHU': '🏢',
                'GRD': '⬜',
                'DUCTING': '🔄',
                'OTHER': '📋',
                'CUSTOM': '⚙️'
            };
            
            return icons[value] || '📋';
        }
    };

    /**
     * Initialize utilities when DOM is ready
     */
    function initializeUtils() {
        // Setup modal handlers
        if (typeof ModalUtils !== 'undefined') {
            ModalUtils.setupModalHandlers();
        }

        console.log('Shared utilities initialized');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeUtils);
    } else {
        initializeUtils();
    }

    // Export utilities for global access
    window.SharedUtils = {
        Modal: window.ModalUtils,
        Api: window.ApiUtils,
        File: window.FileUtils,
        Format: window.FormatUtils,
        Equipment: window.EquipmentUtils
    };

})();