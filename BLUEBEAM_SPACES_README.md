# BlueBeam Spaces Integration

## Overview
This integration adds BlueBeam Spaces detection and visualization capabilities to the PDF Schedule Extractor. It allows you to:
- Detect existing BlueBeam Spaces in PDF files
- Visualize spaces as colored overlays on the PDF viewer
- View space properties (name, color, opacity, area)
- Navigate to pages containing specific spaces

## Components

### Backend (Python)
1. **bluebeam_space_handler.py** - Core module for detecting BlueBeam Spaces using PyMuPDF
2. **space_api_server.py** - Flask API server providing REST endpoints for space operations

### Frontend (JavaScript)
1. **bluebeam-spaces.js** - JavaScript module for rendering spaces on the PDF canvas
2. **index.html** - Updated with BlueBeam Spaces UI components

## Installation

### 1. Create Virtual Environment
```bash
cd /home/jacobe/pdfExtractor\ -\ v2
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install PyMuPDF Flask flask-cors
```

### 3. Test Installation
```bash
python test_spaces.py
```

## Usage

### 1. Start the API Server
```bash
source venv/bin/activate  # If not already activated
python space_api_server.py
```
The server will start on http://localhost:5000

### 2. Open the Web Interface
Open `index.html` in your web browser

### 3. Load a PDF with BlueBeam Spaces
1. Click "Choose PDF" and select a PDF file
2. Once loaded, click "🔍 Detect Spaces" button
3. Detected spaces will appear as:
   - Colored overlays on the PDF
   - Listed in the sidebar under "🔷 BlueBeam Spaces"

### 4. Interact with Spaces
- **Toggle Visibility**: Click "👁️ Hide/Show Spaces" to toggle space overlays
- **Navigate**: Click on a space in the sidebar to jump to its page
- **Hover**: Hover over a space overlay to see its name
- **Click**: Click on a space overlay for additional details

## API Endpoints

### POST /api/detect_spaces
Upload a PDF file and detect BlueBeam Spaces
```bash
curl -X POST -F "file=@document.pdf" http://localhost:5000/api/detect_spaces
```

### POST /api/detect_spaces_from_path
Detect spaces from a file path (for local testing)
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/document.pdf"}' \
  http://localhost:5000/api/detect_spaces_from_path
```

### GET /api/spaces/<file_hash>
Get cached spaces for a file
```bash
curl http://localhost:5000/api/spaces/<file_hash>
```

## Coordinate System

The integration handles coordinate transformations between:
- **PyMuPDF (Backend)**: Bottom-left origin, Y increases upward
- **PDF.js (Frontend)**: Top-left origin, Y increases downward

Transformations are handled automatically by the `BlueBeamSpaceManager` class.

## Technical Details

### BlueBeam Space Structure
BlueBeam Spaces are custom PDF objects with:
- `/Type /Space` - Object type identifier
- `/Title` - Space name
- `/Path` - Array of coordinate pairs defining the boundary
- `/C` - RGB color (0.0-1.0 range)
- `/CA` - Opacity (0.0-1.0 range)

### Space Detection Process
1. Scan PDF for pages with `/BSISpaces` arrays
2. Extract space references from BSISpaces arrays
3. Parse each Space object to extract properties
4. Map spaces to their respective pages
5. Calculate bounds and area for each space

## Troubleshooting

### Server Won't Start
- Ensure virtual environment is activated
- Check if port 5000 is available: `lsof -i :5000`
- Verify Flask is installed: `pip list | grep Flask`

### Spaces Not Detected
- Verify the PDF contains actual BlueBeam Spaces (not just annotations)
- Check browser console for JavaScript errors
- Ensure API server is running
- Check CORS is enabled (handled by flask-cors)

### Spaces Not Rendering
- Check browser console for coordinate transformation errors
- Verify zoom level is being properly handled
- Ensure overlay container is created

### Test with Sample PDF
```bash
# Test detection directly
source venv/bin/activate
python bluebeam_space_handler.py /path/to/pdf_with_spaces.pdf
```

## Future Enhancements
- Create new BlueBeam Spaces
- Edit existing space properties
- Delete spaces
- Export spaces to JSON/CSV
- Batch process multiple PDFs
- Integration with schedule extraction workflow