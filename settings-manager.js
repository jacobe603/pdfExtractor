/**
 * Settings Manager for PDF Schedule Extractor
 * Handles configuration loading, saving, and management
 */

class SettingsManager {
    constructor() {
        this.defaultConfig = null;
        this.userSettings = {};
        this.configUrl = 'config.json';
        this.storageKey = 'pdfExtractorSettings';
    }

    /**
     * Initialize settings by loading config and user preferences
     */
    async init() {
        try {
            // Load default config
            await this.loadDefaultConfig();
            
            // Load user settings from localStorage
            this.loadUserSettings();
            
            // Merge settings
            this.settings = this.mergeSettings();
            
            console.log('Settings Manager initialized:', this.settings);
            return this.settings;
        } catch (error) {
            console.error('Failed to initialize settings:', error);
            // Return minimal fallback settings
            return this.getFallbackSettings();
        }
    }

    /**
     * Load default configuration from config.json
     */
    async loadDefaultConfig() {
        try {
            const response = await fetch(this.configUrl);
            if (!response.ok) {
                throw new Error(`Failed to load config: ${response.status}`);
            }
            this.defaultConfig = await response.json();
            console.log('Default config loaded:', this.defaultConfig);
        } catch (error) {
            console.error('Error loading config.json:', error);
            this.defaultConfig = this.getFallbackSettings();
        }
    }

    /**
     * Load user settings from localStorage
     */
    loadUserSettings() {
        try {
            const stored = localStorage.getItem(this.storageKey);
            if (stored) {
                this.userSettings = JSON.parse(stored);
                console.log('User settings loaded:', this.userSettings);
            }
        } catch (error) {
            console.error('Error loading user settings:', error);
            this.userSettings = {};
        }
    }

    /**
     * Save user settings to localStorage
     */
    saveUserSettings(settings) {
        try {
            // Merge with existing user settings
            this.userSettings = { ...this.userSettings, ...settings };
            
            // Save to localStorage
            localStorage.setItem(this.storageKey, JSON.stringify(this.userSettings));
            
            // Update current settings
            this.settings = this.mergeSettings();
            
            console.log('Settings saved:', this.userSettings);
            return true;
        } catch (error) {
            console.error('Error saving settings:', error);
            return false;
        }
    }

    /**
     * Merge default config with user settings
     */
    mergeSettings() {
        if (!this.defaultConfig) {
            return this.userSettings;
        }

        // Deep merge settings
        const merged = JSON.parse(JSON.stringify(this.defaultConfig)); // Deep clone
        
        // Override with user settings
        if (this.userSettings.equipmentTypes) {
            merged.equipmentTypes = this.userSettings.equipmentTypes;
        }
        
        if (this.userSettings.extractionTypes) {
            merged.extractionTypes = this.userSettings.extractionTypes;
        }
        
        if (this.userSettings.searchPresets) {
            merged.searchPresets = this.userSettings.searchPresets;
        }
        
        if (this.userSettings.defaultSettings) {
            merged.defaultSettings = { ...merged.defaultSettings, ...this.userSettings.defaultSettings };
        }
        
        // Handle API key separately (always from localStorage)
        const savedApiKey = localStorage.getItem('gemini-api-key');
        if (savedApiKey) {
            if (!merged.apiSettings) merged.apiSettings = {};
            merged.apiSettings.geminiApiKey = savedApiKey;
        }
        
        return merged;
    }

    /**
     * Get current settings
     */
    getSettings() {
        return this.settings || this.getFallbackSettings();
    }

    /**
     * Get specific setting value
     */
    getSetting(path) {
        const keys = path.split('.');
        let value = this.settings;
        
        for (const key of keys) {
            if (value && typeof value === 'object' && key in value) {
                value = value[key];
            } else {
                return undefined;
            }
        }
        
        return value;
    }

    /**
     * Update specific setting
     */
    setSetting(path, value) {
        const keys = path.split('.');
        const lastKey = keys.pop();
        
        // Navigate to the parent object
        let current = this.userSettings;
        for (const key of keys) {
            if (!(key in current) || typeof current[key] !== 'object') {
                current[key] = {};
            }
            current = current[key];
        }
        
        // Set the value
        current[lastKey] = value;
        
        // Save to localStorage
        return this.saveUserSettings(this.userSettings);
    }

    /**
     * Add custom equipment type
     */
    addEquipmentType(value, label) {
        const equipmentTypes = this.settings.equipmentTypes || [];
        
        // Check if already exists
        if (equipmentTypes.find(et => et.value === value)) {
            console.warn(`Equipment type ${value} already exists`);
            return false;
        }
        
        // Add new type
        equipmentTypes.push({ value, label });
        
        // Save
        return this.saveUserSettings({ equipmentTypes });
    }

    /**
     * Remove equipment type
     */
    removeEquipmentType(value) {
        const equipmentTypes = this.settings.equipmentTypes || [];
        const filtered = equipmentTypes.filter(et => et.value !== value);
        
        if (filtered.length === equipmentTypes.length) {
            console.warn(`Equipment type ${value} not found`);
            return false;
        }
        
        return this.saveUserSettings({ equipmentTypes: filtered });
    }

    /**
     * Add search preset
     */
    addSearchPreset(term) {
        const searchPresets = this.settings.searchPresets || [];
        
        if (searchPresets.includes(term)) {
            console.warn(`Search preset ${term} already exists`);
            return false;
        }
        
        searchPresets.push(term);
        return this.saveUserSettings({ searchPresets });
    }

    /**
     * Remove search preset
     */
    removeSearchPreset(term) {
        const searchPresets = this.settings.searchPresets || [];
        const filtered = searchPresets.filter(p => p !== term);
        
        if (filtered.length === searchPresets.length) {
            console.warn(`Search preset ${term} not found`);
            return false;
        }
        
        return this.saveUserSettings({ searchPresets: filtered });
    }

    /**
     * Export settings to JSON file
     */
    exportSettings() {
        const exportData = {
            ...this.settings,
            exportDate: new Date().toISOString(),
            version: this.settings.version || '1.0.0'
        };
        
        // Remove sensitive data
        if (exportData.apiSettings && exportData.apiSettings.geminiApiKey) {
            delete exportData.apiSettings.geminiApiKey;
        }
        
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pdf-extractor-settings-${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('Settings exported');
    }

    /**
     * Import settings from JSON file
     */
    async importSettings(file) {
        try {
            const text = await file.text();
            const imported = JSON.parse(text);
            
            // Validate imported settings
            if (!imported.equipmentTypes || !imported.extractionTypes) {
                throw new Error('Invalid settings file format');
            }
            
            // Remove sensitive data from import
            if (imported.apiSettings && imported.apiSettings.geminiApiKey) {
                delete imported.apiSettings.geminiApiKey;
            }
            
            // Save imported settings
            this.userSettings = imported;
            this.saveUserSettings(this.userSettings);
            
            console.log('Settings imported successfully');
            return true;
        } catch (error) {
            console.error('Error importing settings:', error);
            alert('Failed to import settings: ' + error.message);
            return false;
        }
    }

    /**
     * Reset to default settings
     */
    resetToDefaults() {
        // Clear user settings
        this.userSettings = {};
        localStorage.removeItem(this.storageKey);
        
        // Reload settings
        this.settings = this.defaultConfig || this.getFallbackSettings();
        
        console.log('Settings reset to defaults');
        return true;
    }

    /**
     * Get fallback settings if config fails to load
     */
    getFallbackSettings() {
        return {
            equipmentTypes: [
                { value: 'FANS', label: 'FANS' },
                { value: 'VAV', label: 'VAV' },
                { value: 'RTU', label: 'RTU' },
                { value: 'AHU', label: 'AHU' },
                { value: 'OTHER', label: 'OTHER' }
            ],
            extractionTypes: [
                { value: 'schedule', label: 'Schedule' },
                { value: 'drawing', label: 'Drawing' },
                { value: 'table', label: 'Table' },
                { value: 'other', label: 'Other' }
            ],
            defaultSettings: {
                defaultEquipmentType: 'FANS',
                defaultExtractionType: 'schedule',
                enableTextExtraction: true,
                autoRunOCR: false,
                ocrProvider: 'auto'
            },
            searchPresets: ['CFM', 'HP', 'RPM'],
            apiSettings: {},
            version: '1.0.0'
        };
    }

    /**
     * Update UI elements with current settings
     */
    applySettingsToUI() {
        // Update equipment type dropdown
        const equipmentSelect = document.getElementById('equipment-type');
        if (equipmentSelect) {
            // Clear existing options
            equipmentSelect.innerHTML = '';
            
            // Add options from settings
            this.settings.equipmentTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.value;
                option.textContent = type.label;
                equipmentSelect.appendChild(option);
            });
            
            // Set default value
            equipmentSelect.value = this.settings.defaultSettings.defaultEquipmentType;
        }
        
        // Update extraction type dropdown
        const extractionSelect = document.getElementById('extraction-type');
        if (extractionSelect) {
            extractionSelect.innerHTML = '';
            
            this.settings.extractionTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.value;
                option.textContent = type.label;
                extractionSelect.appendChild(option);
            });
            
            extractionSelect.value = this.settings.defaultSettings.defaultExtractionType;
        }
        
        // Update text extraction toggle
        const textExtractionToggle = document.getElementById('enable-text-extraction');
        if (textExtractionToggle) {
            textExtractionToggle.checked = this.settings.defaultSettings.enableTextExtraction;
        }
        
        // Update OCR provider
        const ocrProviderSelect = document.getElementById('ocr-provider');
        if (ocrProviderSelect) {
            ocrProviderSelect.value = this.settings.defaultSettings.ocrProvider;
        }
        
        console.log('Settings applied to UI');
    }
}

// Create global instance
window.settingsManager = new SettingsManager();