/**
 * BlueBeam Spaces JavaScript Module
 * ==================================
 * 
 * Handles detection, visualization, and management of BlueBeam Spaces in PDF viewer.
 */

class BlueBeamSpaceManager {
    constructor() {
        // Use dynamic hostname like the main app
        this.apiUrl = `http://${window.location.hostname}:5000/api`;
        this.spaces = [];
        this.pageSpaces = {}; // Spaces organized by page number
        this.spacesVisible = true;
        this.spaceOverlays = new Map(); // DOM elements for space overlays
        this.currentPageNum = 1;
        this.currentZoom = 1.0;
        this.pageHeight = 792; // Default page height in points
        this.pageInfo = {};
        this.importedSpaces = new Set(); // Track which spaces have been imported
    }

    /**
     * Initialize the space manager
     */
    init() {
        console.log('BlueBeam Space Manager initialized');
        this.createSpaceOverlayContainer();
    }

    /**
     * Create container for space overlays
     */
    createSpaceOverlayContainer() {
        // Check if container already exists
        let container = document.getElementById('bluebeam-spaces-overlay');
        if (!container) {
            container = document.createElement('div');
            container.id = 'bluebeam-spaces-overlay';
            container.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 5;
            `;
            
            // Add to canvas container
            const canvasContainer = document.getElementById('canvas-container');
            if (canvasContainer) {
                canvasContainer.appendChild(container);
            }
        }
        this.overlayContainer = container;
    }

    /**
     * Detect spaces in the current PDF
     * @param {File|string} pdfSource - PDF file or path
     */
    async detectSpaces(pdfSource) {
        try {
            let response;
            
            if (pdfSource instanceof File) {
                // Upload file to detect spaces
                const formData = new FormData();
                formData.append('file', pdfSource);
                
                response = await fetch(`${this.apiUrl}/detect_spaces`, {
                    method: 'POST',
                    body: formData
                });
            } else if (typeof pdfSource === 'string') {
                // Use file path
                response = await fetch(`${this.apiUrl}/detect_spaces_from_path`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ pdf_path: pdfSource })
                });
            } else {
                throw new Error('Invalid PDF source');
            }

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.spaces = data.spaces || [];
                this.pageInfo = data.pages || [];
                this.organizeSpacesByPage();
                console.log(`Detected ${this.spaces.length} BlueBeam Spaces`);
                return data;
            } else {
                throw new Error(data.error || 'Failed to detect spaces');
            }
        } catch (error) {
            console.error('Error detecting spaces:', error);
            throw error;
        }
    }

    /**
     * Organize spaces by page number for efficient rendering
     */
    organizeSpacesByPage() {
        this.pageSpaces = {};
        this.spaces.forEach(space => {
            const pageNum = space.page_number;
            if (!this.pageSpaces[pageNum]) {
                this.pageSpaces[pageNum] = [];
            }
            this.pageSpaces[pageNum].push(space);
        });
    }

    /**
     * Convert PyMuPDF rect to PDF.js canvas coordinates
     * Uses the pre-transformed pymupdf_rect from backend which already handles rotation
     * 
     * @param {Array} pymupdfRect - [x0, y0, x1, y1] rectangle from backend transformation
     * @param {number} zoom - Current zoom level
     * @param {number} rotation - Page rotation angle for UI correction
     * @param {number} pageWidth - Page width for origin correction (rotated dimensions)
     * @param {number} pageHeight - Page height for rotation transformations
     * @returns {Object} Bounding box for canvas positioning
     */
    transformPyMuPDFRect(pymupdfRect, zoom, rotation = 0, pageWidth = 0, pageHeight = 0) {
        if (!pymupdfRect || pymupdfRect.length < 4) {
            return null;
        }
        
        const displayScale = 1.5 * zoom; // PDF.js uses 1.5 as base scale
        let [x0, y0, x1, y1] = pymupdfRect;
        
        if (rotation === 90) {
            // For 90° rotation: swap X and Y coordinates after scaling
            const tempX0 = y0 * displayScale;
            const tempY0 = x0 * displayScale;
            const tempX1 = y1 * displayScale;
            const tempY1 = x1 * displayScale;
            
            x0 = tempX0;
            y0 = tempY0;
            x1 = tempX1;
            y1 = tempY1;
        } else {
            // For unrotated pages, just apply scaling
            x0 *= displayScale;
            y0 *= displayScale;
            x1 *= displayScale;
            y1 *= displayScale;
        }
        
        return {
            x: Math.min(x0, x1),
            y: Math.min(y0, y1),
            width: Math.abs(x1 - x0),
            height: Math.abs(y1 - y0)
        };
    }

    /**
     * Get bounding box from coordinates
     * @param {Array} coords - Transformed canvas coordinates
     * @returns {Object} Bounding box with x, y, width, height
     */
    getBoundingBox(coords) {
        const xCoords = coords.map(c => c[0]);
        const yCoords = coords.map(c => c[1]);
        
        const minX = Math.min(...xCoords);
        const minY = Math.min(...yCoords);
        const maxX = Math.max(...xCoords);
        const maxY = Math.max(...yCoords);
        
        return {
            x: minX,
            y: minY,
            width: maxX - minX,
            height: maxY - minY
        };
    }

    /**
     * Render spaces for the current page
     * @param {number} pageNum - Zero-based page number
     * @param {number} zoom - Current zoom level
     * @param {number} pageHeight - Page height in points
     * @param {number} pageWidth - Page width in points
     * @param {number} rotation - Page rotation angle
     */
    renderSpacesForPage(pageNum, zoom, pageHeight, pageWidth, rotation = 0) {
        this.currentPageNum = pageNum;
        this.currentZoom = zoom;
        this.pageHeight = pageHeight || this.pageHeight;
        this.pageWidth = pageWidth || 612; // Default to letter size
        
        // Clear existing overlays
        this.clearOverlays();
        
        if (!this.spacesVisible) {
            return;
        }
        
        const spaces = this.pageSpaces[pageNum] || [];
        
        spaces.forEach(space => {
            this.renderSpace(space, zoom, this.pageHeight, this.pageWidth, rotation);
        });
    }

    /**
     * Render a single space overlay
     * @param {Object} space - Space object from backend
     * @param {number} zoom - Current zoom level
     * @param {number} pageHeight - Page height in points (unused now)
     * @param {number} pageWidth - Page width in points (unused now)
     * @param {number} rotation - Page rotation angle (handled by backend)
     */
    renderSpace(space, zoom, pageHeight, pageWidth, rotation = 0) {
        // Use pre-transformed pymupdf_rect from backend with UI rotation correction
        // Pass both pageWidth and pageHeight for coordinate calculations
        const bbox = this.transformPyMuPDFRect(space.pymupdf_rect, zoom, rotation, pageWidth, pageHeight);
        
        if (!bbox) {
            console.warn('No valid pymupdf_rect for space:', space.title);
            return;
        }
        
        
        // Create overlay element
        const overlay = document.createElement('div');
        overlay.className = 'bluebeam-space-overlay';
        overlay.dataset.spaceId = space.xref;
        overlay.dataset.spaceTitle = space.title;
        
        // Check if this space has been imported
        const isImported = this.importedSpaces.has(space.xref);
        
        // Convert color from 0-1 range to 0-255
        let r = Math.round(space.color[0] * 255);
        let g = Math.round(space.color[1] * 255);
        let b = Math.round(space.color[2] * 255);
        
        // If imported, use a different color (green tint)
        if (isImported) {
            r = Math.min(255, r * 0.5);
            g = Math.min(255, g + 100);
            b = Math.min(255, b * 0.5);
        }
        
        // Style the overlay
        overlay.style.cssText = `
            position: absolute;
            left: ${bbox.x}px;
            top: ${bbox.y}px;
            width: ${bbox.width}px;
            height: ${bbox.height}px;
            background-color: rgba(${r}, ${g}, ${b}, ${isImported ? 0.15 : space.opacity * 0.3});
            border: 2px ${isImported ? 'dashed' : 'solid'} rgba(${r}, ${g}, ${b}, ${space.opacity});
            pointer-events: auto;
            cursor: pointer;
            z-index: 4;
        `;
        
        // Add checkmark icon if imported
        if (isImported) {
            const checkmark = document.createElement('div');
            checkmark.style.cssText = `
                position: absolute;
                top: 2px;
                right: 2px;
                width: 20px;
                height: 20px;
                background: rgba(46, 204, 113, 0.9);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                color: white;
                pointer-events: none;
            `;
            checkmark.textContent = '✓';
            overlay.appendChild(checkmark);
        }
        
        // Add hover effect
        overlay.addEventListener('mouseenter', (e) => {
            e.target.style.backgroundColor = `rgba(${r}, ${g}, ${b}, ${space.opacity * 0.5})`;
            this.showSpaceTooltip(e, space);
        });
        
        overlay.addEventListener('mouseleave', (e) => {
            e.target.style.backgroundColor = `rgba(${r}, ${g}, ${b}, ${space.opacity * 0.3})`;
            this.hideSpaceTooltip();
        });
        
        // Add click handler
        overlay.addEventListener('click', (e) => {
            e.stopPropagation();
            this.onSpaceClick(space);
        });
        
        // Add to container
        if (this.overlayContainer) {
            this.overlayContainer.appendChild(overlay);
            this.spaceOverlays.set(space.xref, overlay);
        }
    }

    /**
     * Show tooltip for space on hover
     * @param {Event} event - Mouse event
     * @param {Object} space - Space object
     */
    showSpaceTooltip(event, space) {
        // Remove existing tooltip
        this.hideSpaceTooltip();
        
        const isImported = this.importedSpaces.has(space.xref);
        
        const tooltip = document.createElement('div');
        tooltip.id = 'space-tooltip';
        tooltip.style.cssText = `
            position: absolute;
            left: ${event.pageX + 10}px;
            top: ${event.pageY - 30}px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            z-index: 1000;
            pointer-events: none;
            white-space: nowrap;
        `;
        tooltip.textContent = `${space.title} (Page ${space.page_number + 1})${isImported ? ' ✓ Imported' : ''}`;
        document.body.appendChild(tooltip);
    }

    /**
     * Hide space tooltip
     */
    hideSpaceTooltip() {
        const tooltip = document.getElementById('space-tooltip');
        if (tooltip) {
            tooltip.remove();
        }
    }

    /**
     * Handle space click
     * @param {Object} space - Space object
     */
    onSpaceClick(space) {
        console.log('Space clicked:', space);
        // Trigger custom event that can be handled by main application
        const event = new CustomEvent('spaceClicked', { detail: space });
        document.dispatchEvent(event);
    }

    /**
     * Clear all space overlays
     */
    clearOverlays() {
        this.spaceOverlays.forEach(overlay => overlay.remove());
        this.spaceOverlays.clear();
    }

    /**
     * Toggle space visibility
     * @param {boolean} visible - Whether to show spaces
     */
    setSpacesVisible(visible) {
        this.spacesVisible = visible;
        if (this.overlayContainer) {
            this.overlayContainer.style.display = visible ? 'block' : 'none';
        }
    }

    /**
     * Get spaces for current page
     * @param {number} pageNum - Zero-based page number
     * @returns {Array} Array of spaces for the page
     */
    getSpacesForPage(pageNum) {
        return this.pageSpaces[pageNum] || [];
    }

    /**
     * Get all detected spaces
     * @returns {Array} All spaces
     */
    getAllSpaces() {
        return this.spaces;
    }

    /**
     * Update zoom level and re-render
     * @param {number} zoom - New zoom level
     */
    updateZoom(zoom) {
        if (this.currentZoom !== zoom) {
            this.currentZoom = zoom;
            this.renderSpacesForPage(this.currentPageNum, zoom, this.pageHeight);
        }
    }

    /**
     * Get space statistics
     * @returns {Object} Statistics about detected spaces
     */
    getStatistics() {
        return {
            totalSpaces: this.spaces.length,
            spacesByPage: Object.keys(this.pageSpaces).reduce((acc, pageNum) => {
                acc[pageNum] = this.pageSpaces[pageNum].length;
                return acc;
            }, {}),
            uniqueTitles: [...new Set(this.spaces.map(s => s.title))],
            totalArea: this.spaces.reduce((sum, s) => sum + s.area, 0)
        };
    }
}

// Export for use in main application
window.BlueBeamSpaceManager = BlueBeamSpaceManager;