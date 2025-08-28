#!/usr/bin/env python3
"""
Flask API Server for BlueBeam Space Operations
==============================================

Provides REST API endpoints for detecting and managing BlueBeam Spaces.
"""

from flask import Flask, request, jsonify, send_file, make_response
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
import fitz  # PyMuPDF for PDF generation

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "DELETE", "OPTIONS"]}})  # Enable CORS for all routes

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


def convert_windows_path(windows_path):
    """Convert Windows paths including network drives to WSL paths.
    
    Args:
        windows_path (str): Windows path (e.g., 'S:\\Projects\\file.pdf', 'C:\\Users\\file.pdf')
        
    Returns:
        tuple: (converted_path, error_message) where error_message is None if successful
    """
    if not windows_path:
        return None, "No path provided"
    
    original_path = windows_path
    print(f"Converting Windows path: {original_path}", flush=True)
    
    # Handle network drives and local drives
    if len(windows_path) >= 3 and windows_path[1:3] == ':\\':
        drive_letter = windows_path[0].lower()
        
        if drive_letter == 'c':
            # Standard C: drive handling
            converted_path = windows_path.replace('C:\\', '/mnt/c/').replace('c:\\', '/mnt/c/').replace('\\', '/')
            print(f"Converted C: drive to: {converted_path}", flush=True)
        else:
            # Network or other drives (S:, P:, etc.)
            print(f"Attempting to handle network drive: {drive_letter.upper()}:", flush=True)
            
            # Try different mount point strategies
            potential_mounts = [
                f'/mnt/{drive_letter}',  # WSL auto-mount
                f'/mnt/wsl/{drive_letter}',  # WSL 2 style
            ]
            
            converted_path = None
            for mount_point in potential_mounts:
                test_path = windows_path.replace(f'{drive_letter.upper()}:\\', f'{mount_point}/').replace(f'{drive_letter}:\\', f'{mount_point}/').replace('\\', '/')
                print(f"Testing mount point: {mount_point} -> {test_path}", flush=True)
                
                # Check if the mount point exists
                if os.path.exists(mount_point):
                    print(f"Mount point {mount_point} exists, trying path: {test_path}", flush=True)
                    if os.path.exists(test_path):
                        converted_path = test_path
                        print(f"Successfully found file at: {converted_path}", flush=True)
                        break
                    else:
                        print(f"File not found at: {test_path}", flush=True)
                else:
                    print(f"Mount point does not exist: {mount_point}", flush=True)
            
            if not converted_path:
                # If no WSL mount found, try to suggest workarounds
                error_msg = f"Network drive {drive_letter.upper()}: not accessible from WSL. "
                error_msg += "Try: 1) Copy file to C:\\ drive, 2) Use UNC path (\\\\server\\share), or 3) Mount drive in WSL"
                print(f"Network drive conversion failed: {error_msg}", flush=True)
                return None, error_msg
    
    elif windows_path.startswith('\\\\'):
        # UNC path (\\server\share\path)
        print("UNC path detected, attempting direct access", flush=True)
        converted_path = windows_path.replace('\\', '/')
        
        # UNC paths might not be directly accessible from WSL
        if not os.path.exists(converted_path):
            error_msg = f"UNC path not accessible from WSL: {windows_path}. Try copying file to local drive."
            print(f"UNC path failed: {error_msg}", flush=True)
            return None, error_msg
    
    else:
        # Assume it's already a Unix-style path or relative path
        converted_path = windows_path.replace('\\', '/')
        print(f"Treating as Unix path: {converted_path}", flush=True)
    
    # Final validation
    if converted_path and os.path.exists(converted_path):
        print(f"✅ Path conversion successful: {original_path} -> {converted_path}", flush=True)
        return converted_path, None
    else:
        error_msg = f"Converted path does not exist: {converted_path}"
        print(f"❌ Path conversion failed: {error_msg}", flush=True)
        return None, error_msg


def create_consolidated_equipment_pdfs(export_folder_path):
    """
    Create consolidated PDF files for each equipment type folder with extraction type sorting.
    
    Args:
        export_folder_path (str): Path to the export folder containing equipment directories
        
    Returns:
        int: Number of consolidated PDF files created
    """
    
    # Extraction type priority order (SCHEDULE first, DRAWING second, DETAIL third, others after)
    extraction_type_priority = ['schedule', 'drawing', 'detail', 'table', 'specification', 'other']
    
    def get_extraction_type_priority(extraction_type):
        """Get priority index for sorting (lower = higher priority)"""
        try:
            return extraction_type_priority.index(extraction_type.lower())
        except ValueError:
            # Unknown extraction types go to the end
            return len(extraction_type_priority)
    
    pdfs_created = 0
    
    try:
        # Look for project_data.json to get extraction metadata
        project_data_path = os.path.join(export_folder_path, 'project_data.json')
        extraction_metadata = {}
        
        if os.path.exists(project_data_path):
            print(f"Loading extraction metadata from: {project_data_path}", flush=True)
            with open(project_data_path, 'r') as f:
                project_data = json.load(f)
                
                # Build complete extraction metadata (not just image files)
                extraction_metadata = {}
                for equipment_type, extractions in project_data.get('equipment', {}).items():
                    for extraction in extractions:
                        extraction_id = extraction.get('id', 0)
                        extraction_type = extraction.get('extractionType', 'other')
                        extraction_name = extraction.get('extractionName', 'Unknown')
                        is_full_page = extraction.get('isFullPage', False)
                        
                        # Store metadata by equipment type and ID
                        if equipment_type not in extraction_metadata:
                            extraction_metadata[equipment_type] = []
                            
                        extraction_metadata[equipment_type].append({
                            'id': extraction_id,
                            'type': extraction_type,
                            'name': extraction_name,
                            'is_full_page': is_full_page,
                            'page_number': extraction.get('coordinates', {}).get('page', 1) if is_full_page else None,
                            'image_file': extraction.get('files', {}).get('image') if not is_full_page else None
                        })
        else:
            print("No project_data.json found, using filename-based sorting", flush=True)
        
        # Get the original PDF path for full page extractions
        original_pdf_path = None
        if project_data and 'originalPdfPath' in project_data:
            original_pdf_path = project_data['originalPdfPath']
        
        # Process each equipment type
        if project_data_path and os.path.exists(project_data_path):
            # Use metadata-driven approach for equipment types with extractions
            for equipment_type, extractions_list in extraction_metadata.items():
                equipment_dir = os.path.join(export_folder_path, equipment_type)
                
                # Skip if equipment directory doesn't exist
                if not os.path.isdir(equipment_dir):
                    continue
                    
                print(f"Processing equipment directory: {equipment_type}", flush=True)
                
                if not extractions_list:
                    print(f"No extractions found for {equipment_type}, skipping", flush=True)
                    continue
                
                # Sort extractions by type priority, then by ID for consistency
                extractions_list.sort(key=lambda x: (get_extraction_type_priority(x['type']), x['id']))
                
                print(f"Creating consolidated PDF for {equipment_type} with {len(extractions_list)} extractions:", flush=True)
                for extraction in extractions_list:
                    content_type = "Full Page" if extraction['is_full_page'] else "PNG Extraction"
                    print(f"  - {extraction['type'].upper()}: {extraction['name']} ({content_type})", flush=True)
                
                # Create consolidated PDF
                consolidated_pdf_path = os.path.join(equipment_dir, f"{equipment_type}_extractions.pdf")
                
                try:
                    doc = fitz.open()
                    
                    for extraction in extractions_list:
                        print(f"Adding page: {extraction['name']} ({extraction['type']})", flush=True)
                        
                        if extraction['is_full_page']:
                            # Handle full page extraction
                            if not original_pdf_path or not os.path.exists(original_pdf_path):
                                print(f"⚠️  Original PDF not found for full page extraction: {extraction['name']}", flush=True)
                                continue
                                
                            print(f"Inserting full PDF page {extraction['page_number']} from {original_pdf_path}", flush=True)
                            
                            # Open source PDF and copy the specific page
                            source_doc = fitz.open(original_pdf_path)
                            page_num = extraction['page_number'] - 1  # Convert to 0-based indexing
                            
                            if page_num < 0 or page_num >= len(source_doc):
                                print(f"❌ Invalid page number {extraction['page_number']} for {extraction['name']}", flush=True)
                                source_doc.close()
                                continue
                                
                            # Insert the full page
                            doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
                            source_doc.close()
                            
                            # Apply flattening and optimization to the inserted page
                            inserted_page_idx = len(doc) - 1  # The page we just inserted
                            inserted_page = doc[inserted_page_idx]
                            
                            print(f"Flattening and optimizing page {extraction['page_number']}...", flush=True)
                            
                            # Step 1: Flatten annotations, form fields, and interactive elements
                            # Remove all annotations (flatten them into the page content)
                            annots_to_remove = []
                            for annot in inserted_page.annots():
                                annots_to_remove.append(annot)
                            
                            for annot in annots_to_remove:
                                # Apply redaction to flatten annotation content
                                try:
                                    annot.update()  # Ensure annotation is rendered
                                except:
                                    pass
                                inserted_page.delete_annot(annot)
                            
                            # Step 2: Remove form fields and widgets
                            for widget in inserted_page.widgets():
                                try:
                                    inserted_page.delete_widget(widget)
                                except:
                                    pass
                            
                            # Step 3: Clean and optimize page content streams
                            inserted_page.clean_contents()  # Optimize content stream
                            
                            # Step 4: Remove optional content groups (layers) by flattening them
                            try:
                                # Get the page's resources and remove optional content references
                                page_resources = inserted_page.get_contents()
                                if page_resources:
                                    # This helps flatten any layer-based content
                                    inserted_page.wrap_contents()
                            except Exception as e:
                                print(f"Note: Could not optimize page layers: {str(e)}", flush=True)
                            
                        else:
                            # Handle PNG-based extraction 
                            if not extraction['image_file']:
                                print(f"⚠️  No image file found for extraction: {extraction['name']}", flush=True)
                                continue
                                
                            png_path = os.path.join(equipment_dir, os.path.basename(extraction['image_file']))
                            
                            if not os.path.exists(png_path):
                                print(f"⚠️  PNG file not found: {png_path}", flush=True)
                                continue
                            
                            # Load and optimize the PNG image before inserting
                            with open(png_path, 'rb') as f:
                                png_data = f.read()
                            
                            # Open image to get dimensions
                            img = fitz.open(png_path)
                            page_rect = img[0].rect
                            img.close()
                            
                            # Create a new page with the same dimensions as the image
                            page = doc.new_page(width=page_rect.width, height=page_rect.height)
                            
                            # Insert image with compression settings for smaller file size
                            # Use JPEG compression for better file size (good quality, much smaller)
                            page.insert_image(page_rect, stream=png_data, keep_proportion=True)
                    
                    # Document-level optimization and scrubbing
                    print("Applying document-level optimizations...", flush=True)
                    
                    # Step 5: Scrub the document to remove sensitive data and optimize structure
                    # This removes unused objects, optimizes cross-reference table, and removes metadata
                    try:
                        doc.scrub(attached_files=True, clean_pages=True, 
                                 remove_links=False, reset_fields=True, 
                                 reset_responses=True)
                        print("Document scrubbing completed", flush=True)
                    except Exception as e:
                        print(f"Note: Document scrubbing had issues: {str(e)}", flush=True)
                    
                    # Step 6: Final garbage collection and resource cleanup
                    # Remove any remaining unused fonts, images, and objects
                    try:
                        # Additional cleanup - remove unused resources
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            # Clean any remaining content issues
                            page.clean_contents()
                        print("Final page content optimization completed", flush=True)
                    except Exception as e:
                        print(f"Note: Final optimization had issues: {str(e)}", flush=True)
                    
                    # Save the consolidated PDF with maximum compression and optimization
                    print("Saving optimized PDF...", flush=True)
                    doc.save(consolidated_pdf_path, 
                            garbage=4,          # Garbage collect unused objects (maximum level)
                            deflate=True,       # Enable deflate compression for streams
                            clean=True,         # Clean and optimize the PDF structure  
                            pretty=False,       # Compress structure (no pretty formatting)
                            encryption=fitz.PDF_ENCRYPT_NONE,  # No encryption overhead
                            permissions=-1,     # No permission restrictions
                            expand=False)       # Keep compressed streams compressed
                    doc.close()
                    
                    print(f"✅ Consolidated PDF created: {consolidated_pdf_path}", flush=True)
                    pdfs_created += 1
                    
                except Exception as pdf_error:
                    print(f"❌ Failed to create consolidated PDF for {equipment_type}: {str(pdf_error)}", flush=True)
        else:
            # Fallback to old PNG-only approach for backwards compatibility
            print("Using fallback PNG-only processing", flush=True)
            
            for item in os.listdir(export_folder_path):
                equipment_dir = os.path.join(export_folder_path, item)
                
                # Skip files, only process directories (equipment folders)
                if not os.path.isdir(equipment_dir):
                    continue
                    
                print(f"Processing equipment directory: {item}", flush=True)
                
                # Collect PNG files in this equipment directory
                png_files = []
                for file in os.listdir(equipment_dir):
                    if file.lower().endswith('.png'):
                        png_path = os.path.join(equipment_dir, file)
                        png_files.append({
                            'path': png_path,
                            'filename': file,
                            'extraction_type': 'other',
                            'extraction_name': os.path.splitext(file)[0],
                            'extraction_id': 0
                        })
                
                if not png_files:
                    print(f"No PNG files found in {item}, skipping", flush=True)
                    continue
                
                # Sort PNG files by extraction type priority, then by ID for consistency
                png_files.sort(key=lambda x: (get_extraction_type_priority(x['extraction_type']), x['extraction_id']))
                
                print(f"Creating consolidated PDF for {item} with {len(png_files)} extractions:", flush=True)
                for png_file in png_files:
                    print(f"  - {png_file['extraction_type'].upper()}: {png_file['extraction_name']}", flush=True)
                
                # Create consolidated PDF
                consolidated_pdf_path = os.path.join(equipment_dir, f"{item}_extractions.pdf")
                
                try:
                    doc = fitz.open()
                    
                    for png_file in png_files:
                        print(f"Adding page: {png_file['extraction_name']} ({png_file['extraction_type']})", flush=True)
                        
                        # Load and optimize the PNG image before inserting
                        with open(png_file['path'], 'rb') as f:
                            png_data = f.read()
                        
                        # Open image to get dimensions
                        img = fitz.open(png_file['path'])
                        page_rect = img[0].rect
                        img.close()
                        
                        # Create a new page with the same dimensions as the image
                        page = doc.new_page(width=page_rect.width, height=page_rect.height)
                        
                        # Insert image with compression settings for smaller file size
                        # Use JPEG compression for better file size (good quality, much smaller)  
                        page.insert_image(page_rect, stream=png_data, keep_proportion=True)
                    
                    # Document-level optimization and scrubbing (PNG-only mode)
                    print("Applying document-level optimizations...", flush=True)
                    
                    # Apply document scrubbing and optimization
                    try:
                        doc.scrub(attached_files=True, clean_pages=True, 
                                 remove_links=False, reset_fields=True, 
                                 reset_responses=True)
                        print("Document scrubbing completed", flush=True)
                    except Exception as e:
                        print(f"Note: Document scrubbing had issues: {str(e)}", flush=True)
                    
                    # Final cleanup for PNG-based pages
                    try:
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            page.clean_contents()
                        print("Final page content optimization completed", flush=True)
                    except Exception as e:
                        print(f"Note: Final optimization had issues: {str(e)}", flush=True)
                    
                    # Save the consolidated PDF with maximum compression and optimization
                    print("Saving optimized PDF...", flush=True)
                    doc.save(consolidated_pdf_path, 
                            garbage=4,          # Garbage collect unused objects (maximum level)
                            deflate=True,       # Enable deflate compression for streams
                            clean=True,         # Clean and optimize the PDF structure  
                            pretty=False,       # Compress structure (no pretty formatting)
                            encryption=fitz.PDF_ENCRYPT_NONE,  # No encryption overhead
                            permissions=-1,     # No permission restrictions
                            expand=False)       # Keep compressed streams compressed
                    doc.close()
                    
                    print(f"✅ Consolidated PDF created: {consolidated_pdf_path}", flush=True)
                    pdfs_created += 1
                    
                except Exception as pdf_error:
                    print(f"❌ Failed to create consolidated PDF for {item}: {str(pdf_error)}", flush=True)
    
    except Exception as e:
        print(f"❌ Error in consolidated PDF creation: {str(e)}", flush=True)
        
    return pdfs_created


def convert_png_to_pdf(png_path):
    """
    Legacy function for individual PNG to PDF conversion.
    Kept for compatibility but not used in consolidated approach.
    """
    try:
        pdf_path = os.path.splitext(png_path)[0] + '.pdf'
        print(f"Converting PNG to PDF: {png_path} -> {pdf_path}", flush=True)
        
        doc = fitz.open()
        img = fitz.open(png_path)
        page_rect = img[0].rect
        page = doc.new_page(width=page_rect.width, height=page_rect.height)
        page.insert_image(page_rect, filename=png_path)
        doc.save(pdf_path)
        doc.close()
        img.close()
        
        print(f"✅ PDF generated successfully: {pdf_path}", flush=True)
        return pdf_path
    except Exception as e:
        print(f"❌ PDF conversion failed for {png_path}: {str(e)}", flush=True)
        return None


@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    """Health check endpoint."""
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = make_response('')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    return jsonify({'status': 'healthy', 'service': 'BlueBeam Space API'})

@app.route('/api/load-api-key', methods=['GET'])
def load_api_key():
    """Load Gemini API key from server-side storage."""
    try:
        api_key_path = os.path.expanduser('~/.gemini_api_key')
        if os.path.exists(api_key_path):
            with open(api_key_path, 'r') as f:
                content = f.read().strip()
                # Skip comment lines and extract the actual key
                lines = content.split('\n')
                api_key = None
                for line in lines:
                    if not line.startswith('#') and line.strip():
                        api_key = line.strip()
                        break
                
                if api_key and api_key != 'YOUR_API_KEY_HERE':
                    return jsonify({'apiKey': api_key})
        
        return jsonify({'apiKey': None})
    except Exception as e:
        print(f"Error loading API key: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-api-key', methods=['POST'])
def save_api_key():
    """Save Gemini API key to server-side storage."""
    try:
        data = request.json
        api_key = data.get('apiKey')
        
        if not api_key:
            return jsonify({'error': 'No API key provided'}), 400
        
        api_key_path = os.path.expanduser('~/.gemini_api_key')
        
        # Write the API key to file
        with open(api_key_path, 'w') as f:
            f.write(f"# Gemini API Key Storage\n")
            f.write(f"# This file is automatically managed by the PDF Extractor application\n")
            f.write(f"{api_key}\n")
        
        # Set secure permissions
        os.chmod(api_key_path, 0o600)
        
        return jsonify({'success': True, 'message': 'API key saved successfully'})
    except Exception as e:
        print(f"Error saving API key: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to prevent 404 errors."""
    return '', 204

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
    """Export as folder structure to same directory as PDF."""
    try:
        import zipfile
        import shutil
        
        data = request.get_json()
        pdf_path = data.get('pdf_path')
        zip_data = data.get('zip_data')  # Base64 encoded ZIP
        include_pdfs = data.get('include_pdfs', False)  # New: whether to generate PDFs
        
        if not pdf_path or not zip_data:
            return jsonify({'error': 'Missing pdf_path or zip_data'}), 400
        
        # Remove any surrounding quotes from the path
        pdf_path = pdf_path.strip('"').strip("'")
        
        print(f"Received PDF path: {pdf_path}", flush=True)
        
        # Convert Windows path to WSL path if necessary
        converted_path, error_msg = convert_windows_path(pdf_path)
        if error_msg:
            return jsonify({'error': f'Path conversion failed: {error_msg}'}), 400
        pdf_path = converted_path
        
        # Get directory and name of PDF
        pdf_dir = os.path.dirname(pdf_path)
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Create export folder name with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Limit filename length to avoid issues
        safe_pdf_name = pdf_name[:50] if len(pdf_name) > 50 else pdf_name
        export_folder_name = f"{safe_pdf_name}_extractions_{timestamp}"
        export_folder_path = os.path.join(pdf_dir, export_folder_name)
        
        print(f"Creating export folder: {export_folder_path}", flush=True)
        
        # Create temporary ZIP file first
        temp_zip_path = os.path.join(pdf_dir, f"temp_{timestamp}.zip")
        
        # Decode and save ZIP file temporarily
        zip_bytes = base64.b64decode(zip_data)
        with open(temp_zip_path, 'wb') as f:
            f.write(zip_bytes)
        
        # Extract ZIP to folder
        try:
            # Create the export folder
            os.makedirs(export_folder_path, exist_ok=True)
            
            # Extract ZIP contents to folder
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(export_folder_path)
            
            print(f"Export folder created successfully: {export_folder_path}", flush=True)
            
            # Generate consolidated PDF versions if requested
            if include_pdfs:
                print(f"Generating consolidated PDFs by equipment type (include_pdfs={include_pdfs})...", flush=True)
                
                # Create consolidated PDFs with extraction type sorting
                pdfs_created = create_consolidated_equipment_pdfs(export_folder_path)
                
                if pdfs_created > 0:
                    print(f"✅ Generated {pdfs_created} consolidated PDF files (one per equipment type)", flush=True)
                else:
                    print("⚠️  No consolidated PDFs were created (no equipment folders or PNG files found)", flush=True)
            else:
                print("PDF generation skipped (include_pdfs=False)", flush=True)
            
            # Clean up temporary ZIP file
            os.remove(temp_zip_path)
            
            return jsonify({
                'success': True,
                'path': export_folder_path,
                'filename': export_folder_name,
                'message': f'Exported to folder: {export_folder_name}',
                'is_folder': True
            })
            
        except Exception as extract_error:
            # Clean up temp file if extraction fails
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            raise extract_error
        
    except Exception as e:
        print(f"Error exporting to local: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/browse', methods=['GET'])
def browse_files():
    """Browse for PDF files in common directories."""
    try:
        import platform
        from pathlib import Path
        
        # Get the starting directory from query params or use defaults
        start_dir = request.args.get('path', '')
        
        # Common directories to search
        if not start_dir:
            if platform.system() == 'Windows' or os.path.exists('/mnt/c'):
                # Windows or WSL
                user_home = os.path.expanduser('~')
                if '/mnt/c' in user_home or os.path.exists('/mnt/c'):
                    # WSL environment
                    common_dirs = [
                        '/mnt/c/Users',
                        os.getcwd(),
                    ]
                else:
                    # Native Windows
                    common_dirs = [
                        str(Path.home() / 'Documents'),
                        str(Path.home() / 'Downloads'),
                        str(Path.home() / 'Desktop'),
                        os.getcwd(),
                    ]
            else:
                # Linux/Mac
                common_dirs = [
                    str(Path.home() / 'Documents'),
                    str(Path.home() / 'Downloads'),
                    str(Path.home() / 'Desktop'),
                    os.getcwd(),
                ]
        else:
            common_dirs = [start_dir]
        
        files = []
        folders = []
        
        for directory in common_dirs:
            if os.path.exists(directory):
                try:
                    for item in os.listdir(directory):
                        item_path = os.path.join(directory, item)
                        if os.path.isdir(item_path):
                            folders.append({
                                'name': item,
                                'path': item_path,
                                'type': 'folder'
                            })
                        elif item.lower().endswith('.pdf'):
                            stat = os.stat(item_path)
                            files.append({
                                'name': item,
                                'path': item_path,
                                'size': stat.st_size,
                                'modified': stat.st_mtime,
                                'type': 'file'
                            })
                except PermissionError:
                    continue
        
        # Sort folders first, then files
        folders.sort(key=lambda x: x['name'].lower())
        files.sort(key=lambda x: x['name'].lower())
        
        return jsonify({
            'success': True,
            'current_dir': start_dir or 'Common Locations',
            'folders': folders,
            'files': files,
            'parent': os.path.dirname(start_dir) if start_dir else None
        })
        
    except Exception as e:
        print(f"Error browsing files: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/find-file', methods=['POST'])
def find_file():
    """Find a file by name, size, and modified date."""
    try:
        import platform
        from pathlib import Path
        
        data = request.get_json()
        file_name = data.get('name')
        file_size = data.get('size')
        file_modified = data.get('modified')
        
        if not file_name:
            return jsonify({'error': 'File name required'}), 400
        
        # Common directories to search
        if platform.system() == 'Windows' or os.path.exists('/mnt/c'):
            if os.path.exists('/mnt/c'):
                # WSL
                search_dirs = [
                    '/mnt/c/Users',
                ]
                # Add specific user directories if we can find them
                for user_dir in os.listdir('/mnt/c/Users'):
                    user_path = f'/mnt/c/Users/{user_dir}'
                    if os.path.isdir(user_path):
                        search_dirs.extend([
                            f'{user_path}/Documents',
                            f'{user_path}/Downloads',
                            f'{user_path}/Desktop',
                            f'{user_path}/Claude',
                        ])
            else:
                # Native Windows
                search_dirs = [
                    str(Path.home() / 'Documents'),
                    str(Path.home() / 'Downloads'),
                    str(Path.home() / 'Desktop'),
                ]
        else:
            search_dirs = [
                str(Path.home() / 'Documents'),
                str(Path.home() / 'Downloads'),
                str(Path.home() / 'Desktop'),
            ]
        
        # Add current directory
        search_dirs.append(os.getcwd())
        
        matches = []
        
        for directory in search_dirs:
            if os.path.exists(directory):
                for root, dirs, files in os.walk(directory):
                    # Skip hidden directories
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    for file in files:
                        if file == file_name:
                            file_path = os.path.join(root, file)
                            try:
                                stat = os.stat(file_path)
                                # Check if size matches (if provided)
                                if file_size and abs(stat.st_size - file_size) > 100:
                                    continue
                                
                                matches.append({
                                    'path': file_path,
                                    'size': stat.st_size,
                                    'modified': stat.st_mtime,
                                    'exact_match': stat.st_size == file_size if file_size else True
                                })
                                
                                # If exact match, return immediately
                                if file_size and stat.st_size == file_size:
                                    print(f"Found exact match: {file_path}", flush=True)
                                    return jsonify({
                                        'success': True,
                                        'found': True,
                                        'path': file_path,
                                        'confidence': 'high'
                                    })
                            except:
                                continue
                    
                    # Limit search depth to avoid taking too long
                    if len(matches) > 10:
                        break
        
        if len(matches) == 1:
            print(f"Found unique match: {matches[0]['path']}", flush=True)
            return jsonify({
                'success': True,
                'found': True,
                'path': matches[0]['path'],
                'confidence': 'medium'
            })
        elif len(matches) > 1:
            # Multiple matches, return the most recent
            matches.sort(key=lambda x: x['modified'], reverse=True)
            print(f"Found {len(matches)} matches, returning most recent: {matches[0]['path']}", flush=True)
            return jsonify({
                'success': True,
                'found': True,
                'path': matches[0]['path'],
                'confidence': 'low',
                'multiple_matches': len(matches)
            })
        else:
            print(f"No matches found for {file_name}", flush=True)
            return jsonify({
                'success': True,
                'found': False
            })
        
    except Exception as e:
        print(f"Error finding file: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500



@app.route('/api/load-pdf', methods=['POST'])
def load_pdf():
    """Load a PDF file from the server."""
    try:
        data = request.get_json()
        pdf_path = data.get('path')
        
        if not pdf_path:
            return jsonify({'error': 'No path provided'}), 400
        
        # Convert Windows path to WSL path if necessary
        converted_path, error_msg = convert_windows_path(pdf_path)
        if error_msg:
            return jsonify({'error': f'Path conversion failed: {error_msg}'}), 400
        pdf_path = converted_path
        
        # File existence is already checked in convert_windows_path, but double-check
        if not os.path.exists(pdf_path):
            return jsonify({'error': f'File not found: {pdf_path}'}), 404
        
        # Check if it's a PDF
        if not pdf_path.lower().endswith('.pdf'):
            return jsonify({'error': 'Not a PDF file'}), 400
        
        # Send the file
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=False)
        
    except Exception as e:
        print(f"Error loading PDF: {str(e)}", flush=True)
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


@app.route('/api/browse-extractions', methods=['GET', 'POST'])
def browse_extractions():
    """Browse and load extraction data from exported folders or ZIP files."""
    try:
        if request.method == 'GET':
            # Return available extraction folders
            # Look for common extraction folder patterns
            common_paths = []
            
            # Check current working directory for extraction folders
            cwd = os.getcwd()
            if os.path.exists(cwd):
                for item in os.listdir(cwd):
                    item_path = os.path.join(cwd, item)
                    if os.path.isdir(item_path) and ('extraction' in item.lower() or item.endswith('_extractions')):
                        # Check if it contains project_data.json
                        project_file = os.path.join(item_path, 'project_data.json')
                        if os.path.exists(project_file):
                            common_paths.append({
                                'path': item_path,
                                'name': item,
                                'modified': os.path.getmtime(project_file)
                            })
            
            return jsonify({
                'success': True,
                'extraction_folders': common_paths
            })
            
        else:  # POST request
            data = request.get_json()
            folder_path = data.get('folder_path')
            
            print(f"Loading project data from: {folder_path}", flush=True)
            
            # Convert Windows paths if necessary
            if folder_path:
                converted_path, error_msg = convert_windows_path(folder_path)
                if error_msg:
                    print(f"Folder path conversion failed: {error_msg}", flush=True)
                    return jsonify({'error': f'Folder path conversion failed: {error_msg}'}), 400
                folder_path = converted_path
            
            if not folder_path or not os.path.exists(folder_path):
                print(f"Folder path does not exist: {folder_path}", flush=True)
                return jsonify({'error': 'Invalid folder path'}), 400
                
            project_file = os.path.join(folder_path, 'project_data.json')
            print(f"Looking for project file: {project_file}", flush=True)
            
            if not os.path.exists(project_file):
                print(f"Project file not found: {project_file}", flush=True)
                # List files in directory for debugging
                try:
                    files = os.listdir(folder_path)
                    print(f"Files in directory: {files}", flush=True)
                except:
                    print("Could not list directory contents", flush=True)
                return jsonify({'error': 'No project_data.json found in folder'}), 400
                
            # Load and return project data
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
                
            print(f"Successfully loaded project data with {len(project_data.get('equipment', {}))} equipment types", flush=True)
            
            return jsonify({
                'success': True,
                'project_data': project_data,
                'folder_path': folder_path,
                'original_path': data.get('folder_path')  # Return both converted and original path
            })
            
    except Exception as e:
        print(f"Error browsing extractions: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-extraction/<extraction_id>', methods=['GET'])
def load_extraction_details(extraction_id):
    """Load detailed information about a specific extraction."""
    try:
        # This would typically load from database or file system
        # For now, return a placeholder response
        return jsonify({
            'success': True,
            'message': 'Extraction details endpoint ready for implementation',
            'extraction_id': extraction_id
        })
        
    except Exception as e:
        print(f"Error loading extraction details: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/search-extractions', methods=['POST'])
def search_extractions():
    """Search across extraction OCR text and metadata."""
    try:
        data = request.get_json()
        query = data.get('query', '').lower()
        folder_path = data.get('folder_path')
        
        if not query:
            return jsonify({'error': 'No search query provided'}), 400
            
        results = []
        
        # If folder_path provided, search within that folder
        if folder_path and os.path.exists(folder_path):
            project_file = os.path.join(folder_path, 'project_data.json')
            if os.path.exists(project_file):
                with open(project_file, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                    
                # Search through extractions
                if 'equipment' in project_data:
                    for equipment_type, extractions in project_data['equipment'].items():
                        for extraction in extractions:
                            # Check if query matches any searchable field
                            searchable_text = ' '.join([
                                extraction.get('extractionName', ''),
                                extraction.get('equipmentType', ''),
                                extraction.get('extractionType', ''),
                                extraction.get('ocrData', {}).get('rawText', ''),
                                ' '.join(extraction.get('ocrData', {}).get('notes', {}).get('entries', []))
                            ]).lower()
                            
                            if query in searchable_text:
                                results.append({
                                    'id': extraction.get('id'),
                                    'extractionName': extraction.get('extractionName'),
                                    'equipmentType': equipment_type,
                                    'extractionType': extraction.get('extractionType'),
                                    'relevance': searchable_text.count(query)
                                })
        
        # Sort by relevance
        results.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        
        return jsonify({
            'success': True,
            'results': results,
            'query': query,
            'total_found': len(results)
        })
        
    except Exception as e:
        print(f"Error searching extractions: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/extraction-file/<path:file_path>', methods=['GET'])
def serve_extraction_file(file_path):
    """Serve extraction files (images, JSON, TXT) from extraction folders."""
    try:
        print(f"Serving extraction file: {file_path}", flush=True)
        
        # URL decode the path first
        import urllib.parse
        decoded_path = urllib.parse.unquote(file_path)
        print(f"Decoded path: {decoded_path}", flush=True)
        
        # Ensure the file path is safe and within allowed directories
        safe_path = os.path.normpath(decoded_path)
        print(f"Normalized path: {safe_path}", flush=True)
        
        # Convert Windows paths if running in WSL
        if ((len(safe_path) >= 3 and safe_path[1:3] == ':\\') or 
            safe_path.startswith('/C/') or safe_path.startswith('/c/')):
            
            # Handle /C/ style paths
            if safe_path.startswith('/C/') or safe_path.startswith('/c/'):
                safe_path = safe_path.replace('/C/', 'C:\\').replace('/c/', 'C:\\').replace('/', '\\')
            
            converted_path, error_msg = convert_windows_path(safe_path)
            if error_msg:
                print(f"File path conversion failed: {error_msg}", flush=True)
                return jsonify({'error': f'File path conversion failed: {error_msg}'}), 400
            safe_path = converted_path
        elif safe_path.startswith('mnt/c/'):
            # Add leading slash if it's missing
            safe_path = '/' + safe_path
            print(f"Added leading slash: {safe_path}", flush=True)
        
        print(f"Final path: {safe_path}", flush=True)
        print(f"File exists: {os.path.exists(safe_path)}", flush=True)
        print(f"Is file: {os.path.isfile(safe_path) if os.path.exists(safe_path) else 'N/A'}", flush=True)
        
        # If file doesn't exist at the direct path, try to find it in recent export directories
        if not os.path.exists(safe_path):
            # Check if this looks like a relative path from an export directory
            if '/' in safe_path and not os.path.isabs(safe_path):
                print(f"Searching for relative path in recent exports: {safe_path}", flush=True)
                
                # Get all directories matching *_extractions_* pattern
                import glob
                from pathlib import Path
                
                # Search in current directory and common locations
                search_patterns = [
                    f"*_extractions_*/{safe_path}",
                    f"../*_extractions_*/{safe_path}",
                    f"/mnt/s/Projects/*/*_extractions_*/{safe_path}",
                    f"/home/*/pdfExtractor*/*_extractions_*/{safe_path}"
                ]
                
                found_path = None
                for pattern in search_patterns:
                    matches = glob.glob(pattern)
                    if matches:
                        # Use the most recent match
                        found_path = max(matches, key=os.path.getmtime)
                        print(f"Found file in export directory: {found_path}", flush=True)
                        break
                
                if found_path and os.path.exists(found_path):
                    safe_path = found_path
                else:
                    print(f"File not found in any export directory: {safe_path}", flush=True)
                    return jsonify({'error': f'File not found: {safe_path}'}), 404
            else:
                print(f"File not found: {safe_path}", flush=True)
                return jsonify({'error': f'File not found: {safe_path}'}), 404
            
        if not os.path.isfile(safe_path):
            print(f"Path is not a file: {safe_path}", flush=True)
            return jsonify({'error': f'Path is not a file: {safe_path}'}), 404
            
        # Determine mime type based on extension
        ext = os.path.splitext(safe_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.json': 'application/json',
            '.txt': 'text/plain'
        }
        
        mime_type = mime_types.get(ext, 'application/octet-stream')
        print(f"Serving file with mime type: {mime_type}", flush=True)
        
        return send_file(safe_path, mimetype=mime_type)
        
    except Exception as e:
        print(f"Error serving extraction file: {str(e)}", flush=True)
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
    print("Equipment Browser:")
    print("  GET  /api/browse-extractions - List available extraction folders")
    print("  POST /api/browse-extractions - Load project data from folder")
    print("  GET  /api/load-extraction/<id> - Load extraction details")
    print("  POST /api/search-extractions - Search across extractions")
    print("  GET  /api/extraction-file/<path> - Serve extraction files")
    print("")
    print("Server running on http://localhost:5000")
    print("CORS enabled for all origins")
    
    app.run(host='0.0.0.0', port=5000, debug=True)