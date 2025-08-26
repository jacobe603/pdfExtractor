#!/usr/bin/env python3
"""
Flask API Server for BlueBeam Space Operations
==============================================

Provides REST API endpoints for detecting and managing BlueBeam Spaces.
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import tempfile
import hashlib
import base64
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from bluebeam_space_handler import BlueBeamSpaceHandler

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# In-memory cache for detected spaces (production should use Redis/database)
spaces_cache = {}


def allowed_file(filename):
    """Check if file has allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_hash(file_path):
    """Generate SHA256 hash of file for caching."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'BlueBeam Space API'})


@app.route('/api/detect_spaces', methods=['POST'])
def detect_spaces():
    """
    Detect BlueBeam Spaces in uploaded PDF.
    
    Expects multipart/form-data with 'file' field containing PDF.
    
    Returns:
        JSON with detected spaces and page information
    """
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF files are allowed'}), 400
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        # Check file size
        if os.path.getsize(temp_path) > MAX_FILE_SIZE:
            os.remove(temp_path)
            return jsonify({'error': f'File too large. Maximum size is {MAX_FILE_SIZE/1024/1024}MB'}), 400
        
        # Generate file hash for caching
        file_hash = get_file_hash(temp_path)
        
        # Check cache first
        if file_hash in spaces_cache:
            print(f"Returning cached spaces for {filename}")
            result = spaces_cache[file_hash]
        else:
            # Detect spaces using handler
            print(f"Detecting spaces in {filename}")
            with BlueBeamSpaceHandler(temp_path) as handler:
                spaces = handler.detect_all_spaces()
                
                # Prepare response data
                result = {
                    'success': True,
                    'filename': filename,
                    'file_hash': file_hash,
                    'page_count': handler.doc.page_count,
                    'total_spaces': len(spaces),
                    'spaces': [space.to_dict() for space in spaces],
                    'pages': []
                }
                
                # Add page information
                for page_num in range(handler.doc.page_count):
                    page_info = handler.get_page_info(page_num)
                    page_spaces = handler.get_spaces_for_page(page_num)
                    page_info['space_count'] = len(page_spaces)
                    page_info['space_titles'] = [s.title for s in page_spaces]
                    result['pages'].append(page_info)
                
                # Cache the result
                spaces_cache[file_hash] = result
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error detecting spaces: {e}")
        # Clean up on error
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/detect_spaces_from_path', methods=['POST'])
def detect_spaces_from_path():
    """
    Detect BlueBeam Spaces from a file path (for local testing).
    
    Expects JSON with 'pdf_path' field.
    
    Returns:
        JSON with detected spaces and page information
    """
    try:
        data = request.get_json()
        if not data or 'pdf_path' not in data:
            return jsonify({'error': 'No pdf_path provided'}), 400
        
        pdf_path = data['pdf_path']
        
        # Verify file exists
        if not os.path.exists(pdf_path):
            return jsonify({'error': f'File not found: {pdf_path}'}), 404
        
        # Generate file hash for caching
        file_hash = get_file_hash(pdf_path)
        
        # Check cache first
        if file_hash in spaces_cache:
            print(f"Returning cached spaces for {pdf_path}")
            return jsonify(spaces_cache[file_hash])
        
        # Detect spaces
        print(f"Detecting spaces in {pdf_path}")
        with BlueBeamSpaceHandler(pdf_path) as handler:
            spaces = handler.detect_all_spaces()
            
            # Prepare response data
            result = {
                'success': True,
                'filename': os.path.basename(pdf_path),
                'file_hash': file_hash,
                'page_count': handler.doc.page_count,
                'total_spaces': len(spaces),
                'spaces': [space.to_dict() for space in spaces],
                'pages': []
            }
            
            # Add page information
            for page_num in range(handler.doc.page_count):
                page_info = handler.get_page_info(page_num)
                page_spaces = handler.get_spaces_for_page(page_num)
                page_info['space_count'] = len(page_spaces)
                page_info['space_titles'] = [s.title for s in page_spaces]
                result['pages'].append(page_info)
            
            # Cache the result
            spaces_cache[file_hash] = result
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error detecting spaces: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/spaces/<file_hash>', methods=['GET'])
def get_cached_spaces(file_hash):
    """
    Get cached spaces for a file hash.
    
    Args:
        file_hash: SHA256 hash of the PDF file
        
    Returns:
        JSON with cached spaces or 404 if not found
    """
    if file_hash in spaces_cache:
        return jsonify(spaces_cache[file_hash])
    else:
        return jsonify({'error': 'Spaces not found in cache'}), 404


@app.route('/api/clear_cache', methods=['POST'])
def clear_cache():
    """Clear the spaces cache."""
    spaces_cache.clear()
    return jsonify({'success': True, 'message': 'Cache cleared'})


@app.route('/api/cache_stats', methods=['GET'])
def cache_stats():
    """Get cache statistics."""
    return jsonify({
        'cached_files': len(spaces_cache),
        'file_hashes': list(spaces_cache.keys()),
        'total_spaces': sum(data['total_spaces'] for data in spaces_cache.values())
    })


# ============================================================
# SESSION MANAGEMENT ENDPOINTS
# ============================================================

@app.route('/api/session/save', methods=['POST'])
def save_session():
    """Save session file alongside PDF."""
    try:
        data = request.get_json()
        pdf_path = data.get('pdf_path')
        session_data = data.get('session_data')
        
        if not pdf_path or not session_data:
            return jsonify({'error': 'Missing pdf_path or session_data'}), 400
        
        # Create session file path
        session_path = f"{pdf_path}.pdfextractor.json"
        
        # Save session data
        with open(session_path, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'path': session_path,
            'message': f'Session saved to {os.path.basename(session_path)}'
        })
        
    except Exception as e:
        print(f"Error saving session: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/session/load', methods=['GET'])
def load_session():
    """Load session file if exists."""
    try:
        pdf_path = request.args.get('pdf_path')
        
        if not pdf_path:
            return jsonify({'error': 'No pdf_path provided'}), 400
        
        # Check for session file
        session_path = f"{pdf_path}.pdfextractor.json"
        
        if os.path.exists(session_path):
            with open(session_path, 'r') as f:
                session_data = json.load(f)
            
            # Get file modification time
            last_modified = os.path.getmtime(session_path)
            
            return jsonify({
                'success': True,
                'session': session_data,
                'last_modified': datetime.fromtimestamp(last_modified).isoformat(),
                'path': session_path
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No session found for this PDF'
            })
            
    except Exception as e:
        print(f"Error loading session: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/session/delete', methods=['DELETE'])
def delete_session():
    """Delete session file."""
    try:
        pdf_path = request.args.get('pdf_path')
        
        if not pdf_path:
            return jsonify({'error': 'No pdf_path provided'}), 400
        
        session_path = f"{pdf_path}.pdfextractor.json"
        
        if os.path.exists(session_path):
            os.remove(session_path)
            return jsonify({
                'success': True,
                'message': f'Session deleted: {os.path.basename(session_path)}'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No session file found'
            })
            
    except Exception as e:
        print(f"Error deleting session: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# LOCAL EXPORT ENDPOINTS
# ============================================================

@app.route('/api/export/local', methods=['POST'])
def export_to_local():
    """Export ZIP to same directory as PDF."""
    try:
        data = request.get_json()
        pdf_path = data.get('pdf_path')
        zip_data = data.get('zip_data')  # Base64 encoded ZIP
        
        if not pdf_path or not zip_data:
            return jsonify({'error': 'Missing pdf_path or zip_data'}), 400
        
        # Get directory and name of PDF
        pdf_dir = os.path.dirname(pdf_path)
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Create export filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_name = f"{pdf_name}_extractions_{timestamp}.zip"
        export_path = os.path.join(pdf_dir, export_name)
        
        # Decode and save ZIP file
        zip_bytes = base64.b64decode(zip_data)
        with open(export_path, 'wb') as f:
            f.write(zip_bytes)
        
        return jsonify({
            'success': True,
            'path': export_path,
            'filename': export_name,
            'message': f'Exported to {export_name}'
        })
        
    except Exception as e:
        print(f"Error exporting to local: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/file/info', methods=['POST'])
def get_file_info():
    """Get file path information for uploaded file."""
    try:
        # This endpoint helps track file paths when files are selected
        data = request.get_json()
        file_name = data.get('file_name')
        
        # For now, return a placeholder - in production, you might
        # implement file tracking or use a file browser endpoint
        return jsonify({
            'success': True,
            'message': 'File path tracking requires file browser implementation'
        })
        
    except Exception as e:
        print(f"Error getting file info: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("Starting BlueBeam Space API Server...")
    print("Available endpoints:")
    print("  POST /api/detect_spaces - Upload PDF and detect spaces")
    print("  POST /api/detect_spaces_from_path - Detect spaces from file path")
    print("  GET  /api/spaces/<file_hash> - Get cached spaces")
    print("  POST /api/clear_cache - Clear spaces cache")
    print("  GET  /api/cache_stats - Get cache statistics")
    print("  GET  /api/health - Health check")
    print("")
    print("Session Management:")
    print("  POST /api/session/save - Save session file alongside PDF")
    print("  GET  /api/session/load - Load session from file")
    print("  DELETE /api/session/delete - Delete session file")
    print("")
    print("Local Export:")
    print("  POST /api/export/local - Export ZIP to PDF directory")
    print("")
    print("Server running on http://localhost:5000")
    print("CORS enabled for all origins")
    
    app.run(host='0.0.0.0', port=5000, debug=True)