/**
 * Google Gemini OCR Provider Module
 * Advanced PDF table extraction using Google Gemini API
 * 
 * Dependencies: None (uses native fetch API)
 * Usage: window.GeminiOCRProvider.extractTable(imageData, apiKey)
 */

(function() {
    'use strict';

    // Module configuration
    const CONFIG = {
        geminiApi: {
            baseUrl: 'https://generativelanguage.googleapis.com/v1beta/models',
            model: 'gemini-2.0-flash-exp:generateContent',
            maxRetries: 3,
            timeout: 30000,
            maxImageSize: 20 * 1024 * 1024 // 20MB limit
        },
        tableExtraction: {
            outputFormat: 'markdown',
            includeConfidence: true,
            preserveFormatting: true,
            strictTableDetection: true
        }
    };

    // Processing state
    let isProcessing = false;
    let currentController = null;

    /**
     * Google Gemini OCR Provider class
     */
    class GeminiOCRProvider {
        
        /**
         * Check if Gemini OCR functionality is available
         */
        static isSupported() {
            return typeof fetch !== 'undefined' && 'AbortController' in window;
        }

        /**
         * Extract table from image data using Google Gemini API
         * @param {string} imageData - Base64 image data
         * @param {string} apiKey - Google Gemini API key
         * @returns {Promise<Object>} - Table extraction results
         */
        static async extractTable(imageData, apiKey) {
            if (!this.isSupported()) {
                throw new Error('Gemini OCR not supported in this browser');
            }

            if (!apiKey || apiKey.trim() === '') {
                throw new Error('Gemini API key is required');
            }

            if (isProcessing) {
                throw new Error('Gemini OCR processing already in progress');
            }

            isProcessing = true;
            currentController = new AbortController();
            
            try {
                // Validate and prepare image data
                const preparedImage = this.prepareImageData(imageData);
                
                // Create the API request
                const requestPayload = this.createApiRequest(preparedImage);
                
                // Make API call with timeout
                const response = await this.callGeminiApi(requestPayload, apiKey);
                
                // Process the response
                const tableData = this.processGeminiResponse(response);
                
                return {
                    success: true,
                    provider: 'gemini',
                    confidence: tableData.confidence,
                    text: tableData.rawText || '', // Add text field for compatibility
                    tableData: tableData,
                    markdown: tableData.markdown,
                    rawResponse: response,
                    debug: {
                        model: CONFIG.geminiApi.model,
                        processingTime: Date.now(),
                        imageSize: preparedImage.length
                    }
                };

            } catch (error) {
                console.error('Gemini OCR extraction failed:', error);
                return {
                    success: false,
                    provider: 'gemini',
                    error: error.message,
                    fallbackText: 'Gemini OCR processing failed'
                };
            } finally {
                isProcessing = false;
                currentController = null;
            }
        }

        /**
         * Prepare and validate image data for Gemini API
         * @param {string} imageData - Base64 image data
         * @returns {string} - Prepared image data
         */
        static prepareImageData(imageData) {
            // Remove data URL prefix if present
            let cleanImageData = imageData;
            if (imageData.startsWith('data:image/')) {
                cleanImageData = imageData.split(',')[1];
            }

            // Validate base64 format
            try {
                atob(cleanImageData);
            } catch (error) {
                throw new Error('Invalid base64 image data');
            }

            // Check size limits
            const sizeBytes = (cleanImageData.length * 3) / 4;
            if (sizeBytes > CONFIG.geminiApi.maxImageSize) {
                throw new Error(`Image too large: ${Math.round(sizeBytes / 1024 / 1024)}MB (max: ${CONFIG.geminiApi.maxImageSize / 1024 / 1024}MB)`);
            }

            return cleanImageData;
        }

        /**
         * Create API request payload for Gemini
         * @param {string} imageData - Prepared base64 image data
         * @returns {Object} - API request payload
         */
        static createApiRequest(imageData) {
            const prompt = this.createExtractionPrompt();
            
            return {
                contents: [{
                    parts: [
                        {
                            text: prompt
                        },
                        {
                            inline_data: {
                                mime_type: "image/png",
                                data: imageData
                            }
                        }
                    ]
                }],
                generation_config: {
                    temperature: 0.1,
                    top_k: 40,
                    top_p: 0.95,
                    max_output_tokens: 8192,
                    response_mime_type: "application/json"
                }
            };
        }

        /**
         * Create extraction prompt for Gemini API
         * @returns {string} - Extraction prompt
         */
        static createExtractionPrompt() {
            return `You are a specialized OCR and data extraction system trained to analyze mechanical and construction equipment schedules from drawings, PDFs, and images.

Analyze the provided image and extract all structured table data and accompanying installation notes or annotations. Focus on:

📌 PRIORITY CONTENT:
1. Mechanical equipment schedules, especially for:
   - RTUs, VAVs, FANS, GRDs, etc.
   - Tabular data containing fields like: CFM, HP, ESP, MBH, EER, Voltage, Quantities, Manufacturers, Notes
2. Grouped technical sections like:
   - Supply Fan Section, Exhaust Fan Section, Heating, Cooling Coil, Electrical
3. Footer notes or numbered installation requirements, typically listed below the table

📤 RESPONSE FORMAT (JSON):
{
  "isTable": boolean,
  "confidence": number, // Range: 0 to 100
  "tableData": {
    "rows": number,
    "columns": number,
    "headers": ["header1", "header2", ...],
    "data": [
      ["row1col1", "row1col2", ...],
      ["row2col1", "row2col2", ...]
    ]
  },
  "markdown": "markdown table format",
  "rawText": "All raw extracted text from the image, including any footnotes or annotations",
  "notes": {
    "hasNotes": boolean,
    "count": number,
    "entries": [
      "1) Example installation requirement...",
      "2) Example electrical spec..."
    ]
  },
  "metadata": {
    "tableType": "schedule" | "equipment" | "general",
    "hasHeaders": boolean,
    "estimatedAccuracy": number
  }
}

📌 SPECIAL RULES & CLARIFICATIONS:

✅ Table Detection Requirements
- Only set "isTable": true if the structure has clear column headers and aligned rows
- Do not extract partial or malformed tables

✅ Header Disambiguation
- When fields are repeated across sections (e.g., CFM, HP, Fan Qty for both Supply and Exhaust), disambiguate them using section names, such as:
  - Supply CFM, Exhaust CFM
  - Supply HP, Exhaust HP
  - Supply Fan Qty, Exhaust Fan Qty, etc.
- Use original grouping names from the layout where possible (e.g., Heating, Electrical, Cooling Coil)

✅ Notes/Footnotes Extraction
- Always scan the bottom or side of the image for numbered installation notes or legend text
- If found, populate the notes.entries array and set "hasNotes": true
- Always include these in both rawText and structured notes

✅ Markdown Table
- Return a clean markdown version of the extracted table with properly aligned columns
- Match the header disambiguation used in tableData.headers

✅ Text Clarity Rating
- Set confidence and estimatedAccuracy based on how readable and well-aligned the image content is

The image may contain HVAC schedules, so prioritize recognition of terms like:
RTU, CFM, ESP, MBH, EER, LAT, VFD, MOD, etc.`;
        }

        /**
         * Make API call to Gemini with proper error handling
         * @param {Object} requestPayload - API request payload
         * @param {string} apiKey - API key
         * @returns {Promise<Object>} - API response
         */
        static async callGeminiApi(requestPayload, apiKey) {
            const url = `${CONFIG.geminiApi.baseUrl}/${CONFIG.geminiApi.model}?key=${apiKey}`;
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestPayload),
                signal: currentController.signal
            });

            if (!response.ok) {
                const errorText = await response.text();
                let errorMessage = `Gemini API error: ${response.status}`;
                
                try {
                    const errorData = JSON.parse(errorText);
                    errorMessage = errorData.error?.message || errorMessage;
                } catch (e) {
                    // Use default error message if parsing fails
                }
                
                throw new Error(errorMessage);
            }

            return await response.json();
        }

        /**
         * Process Gemini API response
         * @param {Object} response - Raw API response
         * @returns {Object} - Processed table data
         */
        static processGeminiResponse(response) {
            try {
                // Extract content from Gemini response
                const candidates = response.candidates;
                if (!candidates || candidates.length === 0) {
                    throw new Error('No candidates in Gemini response');
                }

                const content = candidates[0].content;
                if (!content || !content.parts || content.parts.length === 0) {
                    throw new Error('No content in Gemini response');
                }

                const textContent = content.parts[0].text;
                if (!textContent) {
                    throw new Error('No text content in Gemini response');
                }

                // Parse JSON response
                const parsedData = JSON.parse(textContent);
                
                // Validate response structure
                this.validateGeminiResponse(parsedData);
                
                return {
                    isTable: parsedData.isTable,
                    confidence: parsedData.confidence,
                    tableData: parsedData.tableData,
                    markdown: parsedData.markdown,
                    rawText: parsedData.rawText || '',
                    notes: parsedData.notes || { hasNotes: false, count: 0, entries: [] },
                    metadata: parsedData.metadata,
                    rows: parsedData.tableData?.rows || 0,
                    columns: parsedData.tableData?.columns || 0
                };

            } catch (error) {
                console.error('Error processing Gemini response:', error);
                throw new Error(`Failed to process Gemini response: ${error.message}`);
            }
        }

        /**
         * Validate Gemini API response structure
         * @param {Object} data - Parsed response data
         */
        static validateGeminiResponse(data) {
            if (typeof data !== 'object' || data === null) {
                throw new Error('Invalid response format');
            }

            if (typeof data.isTable !== 'boolean') {
                throw new Error('Missing or invalid isTable field');
            }

            if (typeof data.confidence !== 'number' || data.confidence < 0 || data.confidence > 100) {
                throw new Error('Missing or invalid confidence field');
            }

            // rawText is optional - will be provided as empty string if missing

            if (data.isTable) {
                if (!data.tableData || typeof data.tableData !== 'object') {
                    throw new Error('Missing tableData for detected table');
                }

                if (!Array.isArray(data.tableData.headers) || !Array.isArray(data.tableData.data)) {
                    throw new Error('Invalid table structure');
                }
            }

            if (typeof data.markdown !== 'string') {
                throw new Error('Missing or invalid markdown field');
            }
        }

        /**
         * Cancel ongoing processing
         */
        static cancelProcessing() {
            if (currentController) {
                currentController.abort();
                currentController = null;
            }
            isProcessing = false;
        }

        /**
         * Get processing status
         */
        static getStatus() {
            return {
                isProcessing: isProcessing,
                provider: 'gemini',
                model: CONFIG.geminiApi.model
            };
        }
    }

    // Export to global scope
    window.GeminiOCRProvider = GeminiOCRProvider;
    
    // Module ready indicator
    console.log('Gemini OCR Provider module loaded');

})();