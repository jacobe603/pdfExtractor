# How to Run PDF Schedule Extractor

## Quick Start

### Option 1: Run Everything (Recommended)
```bash
python start_all.py
```
This starts both:
- Flask API server (port 5000) - for BlueBeam Spaces and file operations
- HTTP server (port 8080) - to serve the web interface

Then open: 
- **http://localhost:8080** - Main PDF extraction interface
- **http://localhost:8080/equipment-browser.html** - Equipment Browser interface

### Option 2: HTTP Server Only (Basic Features)
```bash
python serve.py
```
- Opens on: **http://localhost:8080**
- Equipment Browser: **http://localhost:8080/equipment-browser.html**
- All features work except BlueBeam Spaces detection and file-based sessions

### Option 3: Use GitHub Pages (No Installation)
Visit: 
- **https://jacobe603.github.io/pdfExtractor/** - Main interface
- **https://jacobe603.github.io/pdfExtractor/equipment-browser.html** - Equipment Browser
- Works without any server
- Limited features (no BlueBeam Spaces, no file-based sessions, config loading may be limited)

## Why Use a Local Server?

Opening `index.html` directly as a file (`file://`) causes:
- ❌ CORS errors when loading config.json
- ❌ Some browser security restrictions
- ❌ Cannot communicate with Flask API

Using a local HTTP server (`http://localhost`):
- ✅ No CORS issues
- ✅ Full browser functionality
- ✅ Can communicate with Flask API
- ✅ Better performance

## Features by Running Method

| Feature | GitHub Pages | HTTP Server Only | Full Setup (Both Servers) |
|---------|--------------|------------------|--------------------------|
| PDF Viewing | ✅ | ✅ | ✅ |
| Manual Extraction | ✅ | ✅ | ✅ |
| OCR (Gemini/Tesseract) | ✅ | ✅ | ✅ |
| Session Save (localStorage) | ✅ | ✅ | ✅ |
| Export ZIP | ✅ | ✅ | ✅ |
| Equipment Browser | ⚠️ | ✅ | ✅ |
| Config Loading | ❌ | ✅ | ✅ |
| BlueBeam Spaces | ❌ | ❌ | ✅ |
| File-based Sessions | ❌ | ❌ | ✅ |
| Export to PDF Folder | ❌ | ❌ | ✅ |

**Note**: ⚠️ = Limited functionality (Equipment Browser works but may have config loading limitations)

## Equipment Browser Usage

### Accessing the Equipment Browser
1. **Start the server** using any method above
2. **Navigate to the Equipment Browser**:
   - Local: `http://localhost:8080/equipment-browser.html`
   - GitHub Pages: `https://jacobe603.github.io/pdfExtractor/equipment-browser.html`

### Loading Extraction Data
The Equipment Browser supports multiple ways to load extraction data:

1. **Drag & Drop Folder**: Drag an exported extraction folder directly into the browser
2. **Load from Current Session**: Load extractions from localStorage
3. **Folder Path** (Full Setup only): Enter a direct path to an extraction folder

### Features
- **Responsive Grid**: Automatically adapts from 4-10 columns based on screen size
- **Equipment Filtering**: Filter by specific equipment types with adaptive layout
- **Complete Image Display**: Shows full PNG extraction content without cropping
- **Mobile Optimized**: Works on tablets and mobile devices with touch-friendly interface

## Troubleshooting

### Port Already in Use
If you see "Port 8080 is already in use":
1. Close other applications using the port
2. Or modify `PORT = 8080` in `serve.py` to use a different port

### Flask Server Not Starting
Ensure dependencies are installed:
```bash
pip install flask flask-cors PyMuPDF
```

### CORS Errors
If you still see CORS errors, you're likely:
- Opening the HTML file directly (use the HTTP server instead)
- Have browser extensions blocking requests (try incognito mode)

## Windows Users
Double-click `serve.bat` to start the HTTP server.