/**
 * OCR Table Extractor Module
 * Standalone module for extracting tables from PDF images using multiple OCR providers
 * 
 * Dependencies: Tesseract.js, GeminiOCRProvider (optional)
 * Usage: window.OCRTableExtractor.extractTable(imageData, options)
 */

(function() {
    'use strict';

    // Module configuration
    const CONFIG = {
        providers: {
            gemini: {
                priority: 1,
                requiresApiKey: true,
                name: 'Google Gemini'
            },
            tesseract: {
                priority: 2,
                requiresApiKey: false,
                name: 'Tesseract.js'
            }
        },
        tesseractOptions: {
            tessedit_pageseg_mode: '6', // Uniform block of text
            tessedit_char_whitelist: '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,()-/:',
        },
        tableDetection: {
            minRowHeight: 20,
            minColumnWidth: 30,
            confidenceThreshold: 60,
            maxRowVariance: 10,
            maxColumnVariance: 15
        }
    };

    // OCR processing state
    let isProcessing = false;
    let currentWorker = null;

    /**
     * Main OCR Table Extractor class
     */
    class OCRTableExtractor {
        
        /**
         * Check if OCR functionality is available
         */
        static isSupported() {
            return this.getAvailableProviders().length > 0;
        }

        /**
         * Get list of available OCR providers
         */
        static getAvailableProviders() {
            const providers = [];
            
            // Check Gemini provider
            if (typeof window.GeminiOCRProvider !== 'undefined' && window.GeminiOCRProvider.isSupported()) {
                providers.push({
                    id: 'gemini',
                    name: CONFIG.providers.gemini.name,
                    priority: CONFIG.providers.gemini.priority,
                    requiresApiKey: CONFIG.providers.gemini.requiresApiKey
                });
            }
            
            // Check Tesseract provider
            if (typeof Tesseract !== 'undefined') {
                providers.push({
                    id: 'tesseract',
                    name: CONFIG.providers.tesseract.name,
                    priority: CONFIG.providers.tesseract.priority,
                    requiresApiKey: CONFIG.providers.tesseract.requiresApiKey
                });
            }
            
            return providers.sort((a, b) => a.priority - b.priority);
        }

        /**
         * Get the best available provider for extraction
         */
        static getBestProvider(options = {}) {
            const providers = this.getAvailableProviders();
            
            // If specific provider requested, check if it's available
            if (options.provider) {
                const requestedProvider = providers.find(p => p.id === options.provider);
                if (requestedProvider) {
                    // Check if API key is provided if required
                    if (requestedProvider.requiresApiKey && !options.apiKey) {
                        throw new Error(`${requestedProvider.name} requires an API key`);
                    }
                    return requestedProvider;
                }
                throw new Error(`Requested provider '${options.provider}' is not available`);
            }
            
            // Find the best available provider
            for (const provider of providers) {
                if (provider.requiresApiKey && !options.apiKey) {
                    continue; // Skip providers that need API key if not provided
                }
                return provider;
            }
            
            throw new Error('No suitable OCR provider available');
        }

        /**
         * Extract table from image data using the best available provider
         * @param {string} imageData - Base64 image data
         * @param {Object} options - Extraction options
         * @param {string} options.provider - Specific provider to use ('gemini' or 'tesseract')
         * @param {string} options.apiKey - API key for providers that require it
         * @returns {Promise<Object>} - Table extraction results
         */
        static async extractTable(imageData, options = {}) {
            if (!this.isSupported()) {
                throw new Error('No OCR providers available');
            }

            if (isProcessing) {
                throw new Error('OCR processing already in progress');
            }

            isProcessing = true;
            
            try {
                // Determine which provider to use
                const provider = this.getBestProvider(options);
                console.log(`Using OCR provider: ${provider.name}`);
                
                let result;
                
                switch (provider.id) {
                    case 'gemini':
                        result = await this.extractWithGemini(imageData, options.apiKey);
                        break;
                    case 'tesseract':
                        result = await this.extractWithTesseract(imageData);
                        break;
                    default:
                        throw new Error(`Unknown provider: ${provider.id}`);
                }
                
                // Add provider info to result
                result.provider = provider.name;
                return result;

            } catch (error) {
                console.error('OCR extraction failed:', error);
                return {
                    success: false,
                    error: error.message,
                    fallbackText: 'OCR processing failed'
                };
            } finally {
                isProcessing = false;
            }
        }

        /**
         * Extract table using Google Gemini API
         * @param {string} imageData - Base64 image data
         * @param {string} apiKey - Gemini API key
         * @returns {Promise<Object>} - Extraction results
         */
        static async extractWithGemini(imageData, apiKey) {
            if (typeof window.GeminiOCRProvider === 'undefined') {
                throw new Error('Gemini OCR provider not available');
            }

            return await window.GeminiOCRProvider.extractTable(imageData, apiKey);
        }

        /**
         * Extract table using Tesseract.js (legacy method)
         * @param {string} imageData - Base64 image data
         * @returns {Promise<Object>} - Extraction results
         */
        static async extractWithTesseract(imageData) {
            if (typeof Tesseract === 'undefined') {
                throw new Error('Tesseract.js not available');
            }

            try {
                // Initialize Tesseract worker with logging
                currentWorker = await Tesseract.createWorker({
                    logger: m => console.log('OCR:', m.status, m.progress || '')
                });
                await currentWorker.loadLanguage('eng');
                await currentWorker.initialize('eng');
                await currentWorker.setParameters(CONFIG.tesseractOptions);

                // Perform OCR
                const { data } = await currentWorker.recognize(imageData);
                
                // Process OCR results
                const tableData = this.processOCRResults(data);
                
                // Generate markdown
                const markdown = this.generateMarkdown(tableData);
                
                return {
                    success: true,
                    confidence: data.confidence,
                    text: data.text,
                    tableData: tableData,
                    markdown: markdown,
                    debug: {
                        wordCount: data.words.length,
                        averageConfidence: this.calculateAverageConfidence(data.words),
                        processingTime: Date.now()
                    }
                };

            } finally {
                // Cleanup
                if (currentWorker) {
                    await currentWorker.terminate();
                    currentWorker = null;
                }
            }
        }

        /**
         * Process OCR results to detect table structure
         * @param {Object} ocrData - Tesseract OCR data
         * @returns {Object} - Processed table data
         */
        static processOCRResults(ocrData) {
            const words = ocrData.words.filter(word => 
                word.confidence > CONFIG.tableDetection.confidenceThreshold
            );

            if (words.length === 0) {
                return {
                    isTable: false,
                    reason: 'No high-confidence text found'
                };
            }

            // Group words by approximate rows
            const rows = this.groupWordsIntoRows(words);
            
            // Group words by approximate columns
            const columns = this.groupWordsIntoColumns(words);
            
            // Detect table structure
            const tableStructure = this.detectTableStructure(rows, columns);
            
            return {
                isTable: tableStructure.isTable,
                rows: tableStructure.rows,
                columns: tableStructure.columns,
                cells: tableStructure.cells,
                confidence: this.calculateTableConfidence(tableStructure),
                debug: {
                    wordCount: words.length,
                    rowCount: rows.length,
                    columnCount: columns.length,
                    rawWords: words
                }
            };
        }

        /**
         * Group words into rows based on Y coordinates
         * @param {Array} words - OCR words with bounding boxes
         * @returns {Array} - Grouped rows
         */
        static groupWordsIntoRows(words) {
            const rows = [];
            const sortedWords = [...words].sort((a, b) => a.bbox.y0 - b.bbox.y0);
            
            for (const word of sortedWords) {
                let foundRow = false;
                
                for (const row of rows) {
                    const rowY = row.words[0].bbox.y0;
                    if (Math.abs(word.bbox.y0 - rowY) < CONFIG.tableDetection.maxRowVariance) {
                        row.words.push(word);
                        foundRow = true;
                        break;
                    }
                }
                
                if (!foundRow) {
                    rows.push({
                        y: word.bbox.y0,
                        words: [word]
                    });
                }
            }
            
            return rows;
        }

        /**
         * Group words into columns based on X coordinates
         * @param {Array} words - OCR words with bounding boxes
         * @returns {Array} - Grouped columns
         */
        static groupWordsIntoColumns(words) {
            const columns = [];
            const sortedWords = [...words].sort((a, b) => a.bbox.x0 - b.bbox.x0);
            
            for (const word of sortedWords) {
                let foundColumn = false;
                
                for (const column of columns) {
                    const columnX = column.words[0].bbox.x0;
                    if (Math.abs(word.bbox.x0 - columnX) < CONFIG.tableDetection.maxColumnVariance) {
                        column.words.push(word);
                        foundColumn = true;
                        break;
                    }
                }
                
                if (!foundColumn) {
                    columns.push({
                        x: word.bbox.x0,
                        words: [word]
                    });
                }
            }
            
            return columns;
        }

        /**
         * Detect table structure from rows and columns
         * @param {Array} rows - Grouped rows
         * @param {Array} columns - Grouped columns
         * @returns {Object} - Table structure
         */
        static detectTableStructure(rows, columns) {
            const minRows = 2;
            const minColumns = 2;
            
            const isTable = rows.length >= minRows && columns.length >= minColumns;
            
            if (!isTable) {
                return {
                    isTable: false,
                    reason: `Insufficient structure: ${rows.length} rows, ${columns.length} columns`
                };
            }
            
            // Create cell grid
            const cells = [];
            
            for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
                const cellRow = [];
                
                for (let colIndex = 0; colIndex < columns.length; colIndex++) {
                    const cell = this.findCellContent(rows[rowIndex], columns[colIndex]);
                    cellRow.push(cell);
                }
                
                cells.push(cellRow);
            }
            
            return {
                isTable: true,
                rows: rows.length,
                columns: columns.length,
                cells: cells
            };
        }

        /**
         * Find content for a specific cell
         * @param {Object} row - Row data
         * @param {Object} column - Column data
         * @returns {Object} - Cell content
         */
        static findCellContent(row, column) {
            const rowY = row.y;
            const colX = column.x;
            
            // Find words that belong to this cell
            const cellWords = row.words.filter(word => 
                Math.abs(word.bbox.x0 - colX) < CONFIG.tableDetection.maxColumnVariance
            );
            
            const text = cellWords.map(word => word.text).join(' ').trim();
            const confidence = cellWords.length > 0 ? 
                cellWords.reduce((sum, word) => sum + word.confidence, 0) / cellWords.length : 0;
            
            return {
                text: text,
                confidence: confidence,
                isEmpty: text.length === 0,
                wordCount: cellWords.length
            };
        }

        /**
         * Generate markdown table from table data
         * @param {Object} tableData - Processed table data
         * @returns {string} - Markdown table
         */
        static generateMarkdown(tableData) {
            if (!tableData.isTable) {
                return `**No table detected**\n\nReason: ${tableData.reason}\n\n**Raw text:**\n${tableData.debug?.rawWords?.map(w => w.text).join(' ') || 'No text found'}`;
            }
            
            const cells = tableData.cells;
            if (cells.length === 0) {
                return '**Empty table detected**';
            }
            
            let markdown = '\n';
            
            // Add table header
            const headerRow = cells[0];
            markdown += '| ' + headerRow.map(cell => cell.text || ' ').join(' | ') + ' |\n';
            
            // Add separator
            markdown += '| ' + headerRow.map(() => '---').join(' | ') + ' |\n';
            
            // Add data rows
            for (let i = 1; i < cells.length; i++) {
                const row = cells[i];
                markdown += '| ' + row.map(cell => cell.text || ' ').join(' | ') + ' |\n';
            }
            
            markdown += '\n';
            
            // Add confidence info
            markdown += `**OCR Confidence:** ${tableData.confidence.toFixed(1)}%\n`;
            markdown += `**Table Size:** ${tableData.rows} rows × ${tableData.columns} columns\n`;
            
            return markdown;
        }

        /**
         * Calculate average confidence of words
         * @param {Array} words - OCR words
         * @returns {number} - Average confidence
         */
        static calculateAverageConfidence(words) {
            if (words.length === 0) return 0;
            const sum = words.reduce((acc, word) => acc + word.confidence, 0);
            return sum / words.length;
        }

        /**
         * Calculate table detection confidence
         * @param {Object} tableStructure - Table structure
         * @returns {number} - Confidence score
         */
        static calculateTableConfidence(tableStructure) {
            if (!tableStructure.isTable) return 0;
            
            let totalConfidence = 0;
            let cellCount = 0;
            
            for (const row of tableStructure.cells) {
                for (const cell of row) {
                    totalConfidence += cell.confidence;
                    cellCount++;
                }
            }
            
            return cellCount > 0 ? totalConfidence / cellCount : 0;
        }
    }

    // Export to global scope
    window.OCRTableExtractor = OCRTableExtractor;
    
    // Module ready indicator
    console.log('OCR Table Extractor module loaded');

})();