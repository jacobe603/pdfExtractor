# PDF Schedule Extractor - Claude Code Integration

## Project Overview
A sophisticated PDF table extraction tool built for construction schedule analysis. The tool allows manual rectangle selection on PDF pages and uses advanced OCR (Google Gemini API and Tesseract.js) to extract table data with equipment-based organization.

## Architecture

### Core Components
- **Frontend**: Vanilla JavaScript with HTML5 Canvas for PDF rendering and selection
- **PDF Processing**: PDF.js library for client-side PDF handling
- **OCR Providers**: 
  - Google Gemini API (primary) - ~95% layout accuracy with advanced notes extraction
  - Tesseract.js (fallback) - local processing
- **Data Storage**: Equipment-organized JSON with individual file generation
- **Batch Processing**: Python script for file organization and reporting

### Key Features
- **Equipment-Based Organization**: Extractions grouped by equipment type (FANS, VAV, GRD, RTU, AHU, DUCTING, CUSTOM)
- **Equipment Browser Interface**: Dedicated responsive interface (`equipment-browser.html`) for viewing and organizing extracted schedules
- **Multi-Type Extractions**: Schedule, Drawing, Table, Detail, Specification, Other
- **Advanced OCR System**: Gemini API with comprehensive notes extraction, Tesseract.js for offline use
- **Installation Notes Extraction**: Automatically captures numbered installation requirements and specifications
- **Comprehensive File Generation**: PNG images, individual PDF files, JSON table data, TXT text files with notes sections
- **Real-time Selection**: Canvas-based rectangle drawing with zoom support
- **PDF Generation**: PNG-to-PDF conversion using PyMuPDF for individual extraction PDFs
- **Adaptive Grid Layout**: Viewport-aware responsive grid system (4-10 columns) with complete image display
- **BlueBeam Spaces Integration**: Detection and visualization of BlueBeam Spaces in PDF files

## File Structure
```
pdfExtractor/
├── index.html                  # Main PDF extraction application
├── equipment-browser.html      # Equipment Browser interface with responsive grid
├── gemini-ocr-provider.js      # Google Gemini API integration
├── ocr-table-extractor.js      # Multi-provider OCR system
├── bluebeam-spaces.js          # BlueBeam Spaces detection and visualization
├── space_api_server.py         # Backend server for PDF processing and space detection
├── batch_processor.py          # Python batch processing
├── config.json                 # Configuration for equipment types and settings
├── CLAUDE.md                   # This file
├── BLUEBEAM_SPACES_README.md   # BlueBeam Spaces documentation
└── README.md                   # User documentation
```

## Development Commands

### Testing
- Open `index.html` in browser for PDF extraction testing
- Open `equipment-browser.html` for Equipment Browser interface testing
- Use browser developer tools for debugging
- Test OCR with sample construction PDFs
- Test Equipment Browser with exported data folders via drag & drop

### Batch Processing
```bash
python batch_processor.py exported_data.json -o organized_schedules -r -v
```

### Linting/Quality
- Use browser developer tools for JavaScript debugging
- Python: `python -m py_compile batch_processor.py`
- No build process required - direct browser execution

## API Integration

### Google Gemini API
- **Model**: gemini-2.0-flash-exp
- **Purpose**: High-accuracy table extraction with comprehensive notes extraction
- **Input**: Base64 image data
- **Output**: Structured JSON with table data, markdown, and installation notes
- **Configuration**: API key stored in localStorage
- **Advanced Features**: 
  - Header disambiguation (Supply CFM vs Exhaust CFM)
  - Automatic footnote detection and extraction
  - Equipment-specific terminology recognition

### Tesseract.js
- **Purpose**: Fallback OCR processing
- **Mode**: Client-side processing
- **Configuration**: Optimized for construction document text

## Data Structure

### Export Format
```json
{
  "project": "Construction Project Name",
  "exportDate": "2024-XX-XX",
  "equipment": {
    "FANS": [
      {
        "extractionName": "Supply Fan Schedule",
        "equipmentType": "FANS",
        "extractionType": "schedule",
        "ocrData": {
          "tableData": {...},
          "markdown": "...",
          "rawText": "...",
          "notes": {
            "hasNotes": true,
            "count": 7,
            "entries": [
              "1) Installation requirement text...",
              "2) Electrical specification..."
            ]
          }
        },
        "files": {
          "image": "FANS/supply_fan_schedule_page2.png",
          "tableData": "FANS/supply_fan_schedule_page2_table.json",
          "textData": "FANS/supply_fan_schedule_page2_text.txt"
        }
      }
    ]
  }
}
```

### Generated Files
- **Main JSON**: Complete project data with equipment grouping and notes
- **Images**: High-resolution PNG extractions
- **PDF Files**: Individual PDF versions of each PNG extraction (optional, enabled by default)
- **Table Data**: Detailed OCR results in JSON format with structured notes
- **Text Files**: Human-readable text with metadata headers and installation notes sections

## Key Functions

### Core Extraction
- `extractImageFromSelection()` - High-resolution image extraction
- `saveSchedule()` - Complete extraction workflow
- `updateExtractionList()` - Equipment-grouped sidebar display

### OCR Processing
- `OCRTableExtractor.extractTable()` - Multi-provider OCR
- `GeminiOCRProvider.extractTable()` - Gemini API integration
- `processTableOCR()` - Immediate OCR processing in modal
- `runOCRForExtraction()` - Post-save OCR processing via extraction card button

### Equipment Management
- `handleEquipmentTypeChange()` - Custom equipment type handling
- `getExtractionTypeIcon()` - Visual type indicators
- Equipment-based file organization

### PDF Generation
- `convert_png_to_pdf()` - Server-side PNG to PDF conversion using PyMuPDF
- Settings-controlled PDF generation (enabled by default)
- Maintains file organization structure with PDF versions alongside PNGs

## Development Notes

### Recent Enhancements
- **Equipment Organization**: Restructured from flat list to equipment-based grouping
- **Enhanced OCR**: Added Gemini API for superior table recognition with notes extraction
- **Installation Notes Integration**: Comprehensive footnote detection and extraction system
- **Multi-File Output**: Individual JSON and TXT files per extraction with notes sections
- **UI Improvements**: Type icons, custom equipment support, better organization, OCR preview with notes
- **Data Structure Compatibility**: Handles both legacy and new OCR data formats
- **Simplified Modal Workflow**: Back-to-basics approach with immediate OCR processing and simplified save function
- **PDF Generation Integration**: Added PyMuPDF-based PNG-to-PDF conversion with settings control

### Technical Decisions
- **Modular OCR**: Separate providers for flexibility and fallback
- **Client-Side Processing**: No server dependency for core functionality
- **Equipment-Centric**: Organized around construction equipment types
- **Backward Compatibility**: Supports both old and new data formats
- **Comprehensive Prompt Engineering**: Advanced Gemini prompts for header disambiguation and notes extraction
- **Structured Notes Storage**: Consistent format for installation requirements across all output types
- **Simplified OCR Workflow**: Removed complex queue systems in favor of immediate processing and post-save options
- **PNG-to-PDF Approach**: Current implementation converts PNG extractions to PDF for simplicity and reliability

### Performance Considerations
- **Canvas Optimization**: Efficient PDF rendering with zoom support
- **Local Storage**: Immediate persistence without server calls
- **Lazy Loading**: PDF pages loaded on demand
- **Memory Management**: Proper cleanup of OCR workers and canvas contexts
- **Responsive Grid Layout**: Viewport-aware sizing with CSS Grid for optimal performance
- **Image Optimization**: Object-fit contain for complete image display without performance impact

## Future Enhancements
- **Equipment Templates**: Pre-configured extraction templates by equipment type
- **Batch OCR**: Process multiple extractions simultaneously
- **Export Formats**: Additional export options (CSV, Excel, etc.)
- **Cloud Integration**: Direct cloud storage integration
- **Mobile Support**: Touch-friendly interface for tablets
- **Vector PDF Generation**: Optional enhancement to extract vector graphics and text directly from PDFs using PyMuPDF's `page.get_drawings()` and `get_text("dict")` for perfect scalable quality (documented 2025-08-27)

## Troubleshooting

### Common Issues
1. **Modal Not Opening**: Check field name consistency between HTML and JavaScript
2. **OCR Failures**: Verify API key configuration and network connectivity
3. **Image Quality**: Ensure high-resolution PDF for better OCR accuracy
4. **File Organization**: Verify batch processor handles both old/new JSON formats

### Debug Mode
- Enable OCR debug info in modal for detailed processing information
- Use browser developer tools for JavaScript debugging
- Check network tab for API call failures

## Testing Scenarios
- **Equipment Types**: Test all predefined and custom equipment types
- **Extraction Types**: Verify schedule, drawing, table, detail, specification, other
- **OCR Providers**: Test both Gemini and Tesseract fallback
- **Notes Extraction**: Test schedules with and without installation notes
- **Header Disambiguation**: Test complex schedules with repeated column names
- **Batch Processing**: Test with various JSON formats and equipment groupings
- **File Generation**: Verify PNG, PDF, JSON, and TXT file creation with notes sections
- **PDF Generation**: Test PNG-to-PDF conversion with and without settings enabled
- **Modal Workflow**: Test immediate OCR in modal, save without OCR, and post-save OCR button
- **UI Workflow**: Test modal preview shows both tables and notes correctly
- **Equipment Browser**: Test responsive grid layout at different screen sizes (desktop, tablet, mobile)
- **Image Display**: Verify complete PNG extraction content is visible without cropping
- **Grid Filtering**: Test equipment type filtering with adaptive column counts
- **Drag & Drop**: Test folder loading functionality in Equipment Browser
- **Viewport Responsiveness**: Test screen space utilization on various screen dimensions

## Recent Enhancements

### Equipment Browser (Version 2.1)
- **Responsive Grid System**: Implemented adaptive CSS Grid layout that scales from 4-10 columns based on viewport width
- **Viewport-Aware Sizing**: Dynamic thumbnail heights using `calc()` functions with `vh` units for optimal screen utilization
- **Complete Image Display**: Fixed image cropping issue by changing from `object-fit: cover` to `object-fit: contain`
- **Enhanced Visual Design**: Added subtle checkerboard backgrounds, borders, shadows, and hover effects
- **Smart Filtering**: Equipment type filters dynamically adjust grid layout (single column for 1 item, max 3 columns for filtered views)
- **Mobile Optimization**: Responsive design with viewport-specific optimizations for tablets and mobile devices

### Technical Implementation
- **CSS Grid Mastery**: Advanced usage of CSS Grid with media queries for responsive breakpoints
- **Viewport Calculations**: Sophisticated use of `calc((100vh - offset) / divisor)` for dynamic sizing
- **Object-Fit Strategy**: Strategic use of `contain` vs `cover` for complete content visibility
- **Performance Optimizations**: Reduced gaps, padding, and improved space utilization without performance impact

This tool represents a comprehensive solution for construction document analysis with modern web technologies, advanced AI integration, and optimized user experience across all device types.