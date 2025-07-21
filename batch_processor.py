#!/usr/bin/env python3
"""
PDF Schedule Extractor - Batch Processing Helper

This script provides batch processing capabilities for the PDF Schedule Extractor.
It can process exported JSON files to organize and manipulate extracted schedule images.
"""

import json
import os
import sys
import base64
import argparse
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

def decode_base64_image(image_data: str, output_path: str) -> bool:
    """
    Decode base64 image data and save to file.
    
    Args:
        image_data: Base64 encoded image data with data URL prefix
        output_path: Path where the image should be saved
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Remove data URL prefix if present
        if image_data.startswith('data:image/'):
            image_data = image_data.split(',')[1]
        
        # Decode base64 data
        image_bytes = base64.b64decode(image_data)
        
        # Write to file
        with open(output_path, 'wb') as f:
            f.write(image_bytes)
        
        return True
    except Exception as e:
        print(f"Error decoding image: {e}")
        return False

def process_extraction_file(json_file: str, output_dir: str) -> Dict[str, Any]:
    """
    Process a JSON extraction file and save images to organized directories.
    
    Args:
        json_file: Path to the JSON file containing extraction data
        output_dir: Directory where organized images should be saved
        
    Returns:
        dict: Processing results and statistics
    """
    results = {
        'total_extractions': 0,
        'successful_saves': 0,
        'failed_saves': 0,
        'created_directories': [],
        'saved_files': [],
        'equipment_types': [],
        'individual_files_created': 0
    }
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Handle both old and new format
        if 'equipment' in data:
            # New equipment-grouped format
            equipment_groups = data['equipment']
            results['equipment_types'] = list(equipment_groups.keys())
            
            # Count total extractions
            total_extractions = sum(len(extractions) for extractions in equipment_groups.values())
            results['total_extractions'] = total_extractions
        else:
            # Old flat format - group by type
            extractions = data.get('extractions', [])
            results['total_extractions'] = len(extractions)
            
            # Group by equipment type for processing
            equipment_groups = {}
            for extraction in extractions:
                equipment_type = extraction.get('equipmentType') or extraction.get('type', 'UNKNOWN')
                if equipment_type not in equipment_groups:
                    equipment_groups[equipment_type] = []
                equipment_groups[equipment_type].append(extraction)
            
            results['equipment_types'] = list(equipment_groups.keys())
        
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Process each equipment type
        for equipment_type, extractions in equipment_groups.items():
            try:
                # Create directory structure based on equipment type
                type_dir = output_path / equipment_type
                type_dir.mkdir(exist_ok=True)
                if str(type_dir) not in results['created_directories']:
                    results['created_directories'].append(str(type_dir))
                
                # Process each extraction in this equipment type
                for extraction in extractions:
                    try:
                        page_num = extraction.get('coordinates', {}).get('page', 'unknown')
                        
                        # Generate filename - support both old and new formats
                        name = extraction.get('extractionName') or extraction.get('name', f'extraction_{extraction.get("id", "unknown")}')
                        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        safe_name = safe_name.replace(' ', '_').lower()
                        
                        filename = f"{safe_name}_page{page_num}.png"
                        image_path = type_dir / filename
                        
                        # Save image
                        image_data = extraction.get('imageData')
                        if image_data and decode_base64_image(image_data, str(image_path)):
                            results['successful_saves'] += 1
                            results['saved_files'].append(str(image_path))
                            
                            # Create metadata file
                            metadata = {
                                'extractionName': extraction.get('extractionName') or extraction.get('name'),
                                'equipmentType': equipment_type,
                                'extractionType': extraction.get('extractionType') or extraction.get('type', 'unknown'),
                                'description': extraction.get('description') or extraction.get('notes'),
                                'coordinates': extraction.get('coordinates'),
                                'timestamp': extraction.get('timestamp'),
                                'extracted_at': datetime.now().isoformat()
                            }
                            
                            metadata_path = image_path.with_suffix('.json')
                            with open(metadata_path, 'w') as f:
                                json.dump(metadata, f, indent=2)
                            results['individual_files_created'] += 1
                            
                            # Create table data file if OCR data exists
                            ocr_data = extraction.get('ocrData')
                            if ocr_data:
                                table_data_path = type_dir / f"{safe_name}_page{page_num}_table.json"
                                with open(table_data_path, 'w') as f:
                                    json.dump(ocr_data, f, indent=2)
                                results['saved_files'].append(str(table_data_path))
                                results['individual_files_created'] += 1
                                
                                # Create text data file
                                text_data_path = type_dir / f"{safe_name}_page{page_num}_text.txt"
                                with open(text_data_path, 'w') as f:
                                    f.write(f"Extraction: {name}\n")
                                    f.write(f"Equipment Type: {equipment_type}\n")
                                    f.write(f"Extraction Type: {extraction.get('extractionType', 'unknown')}\n")
                                    f.write(f"Page: {page_num}\n")
                                    f.write(f"OCR Provider: {ocr_data.get('provider', 'unknown')}\n")
                                    f.write(f"Confidence: {ocr_data.get('confidence', 0)}%\n")
                                    f.write(f"Timestamp: {extraction.get('timestamp', 'unknown')}\n")
                                    f.write("-" * 50 + "\n\n")
                                    f.write("RAW TEXT:\n")
                                    f.write(ocr_data.get('rawText', 'No text data available'))
                                    f.write("\n\n" + "-" * 50 + "\n\n")
                                    f.write("MARKDOWN TABLE:\n")
                                    f.write(ocr_data.get('markdown', 'No table data available'))
                                results['saved_files'].append(str(text_data_path))
                                results['individual_files_created'] += 1
                            
                        else:
                            results['failed_saves'] += 1
                            print(f"Failed to save image for extraction: {name}")
                            
                    except Exception as e:
                        results['failed_saves'] += 1
                        print(f"Error processing extraction {extraction.get('id', 'unknown')}: {e}")
                        
            except Exception as e:
                results['failed_saves'] += 1
                print(f"Error processing equipment type {equipment_type}: {e}")
        
    except Exception as e:
        print(f"Error processing JSON file {json_file}: {e}")
        return results
    
    return results

def process_zip_file(zip_file: str, output_dir: str) -> Dict[str, Any]:
    """
    Process a ZIP file exported from PDF Schedule Extractor.
    
    Args:
        zip_file: Path to the ZIP file containing extraction data
        output_dir: Directory where contents should be extracted
        
    Returns:
        dict: Processing results and statistics
    """
    results = {
        'total_files': 0,
        'extracted_files': 0,
        'annotated_pdf_found': False,
        'annotated_pdf_path': None,
        'project_data_found': False,
        'equipment_types': [],
        'created_directories': [],
        'zip_contents': []
    }
    
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            results['total_files'] = len(file_list)
            results['zip_contents'] = file_list
            
            # Check for annotated PDF
            annotated_pdfs = [f for f in file_list if f.endswith('.pdf') and 'annotated' in f.lower()]
            if annotated_pdfs:
                results['annotated_pdf_found'] = True
                results['annotated_pdf_path'] = annotated_pdfs[0]
            
            # Check for project data
            if 'project_data.json' in file_list:
                results['project_data_found'] = True
                
                # Extract and analyze project data
                project_data = json.loads(zip_ref.read('project_data.json'))
                if 'equipment' in project_data:
                    results['equipment_types'] = list(project_data['equipment'].keys())
            
            # Extract all contents
            zip_ref.extractall(output_path)
            results['extracted_files'] = len(file_list)
            
            # Track created directories
            for item in output_path.rglob('*'):
                if item.is_dir() and str(item) not in results['created_directories']:
                    results['created_directories'].append(str(item))
            
    except Exception as e:
        print(f"Error processing ZIP file {zip_file}: {e}")
        return results
    
    return results

def create_summary_report(results: Dict[str, Any], output_dir: str) -> str:
    """
    Create a summary report of the batch processing results.
    
    Args:
        results: Processing results dictionary
        output_dir: Output directory path
        
    Returns:
        str: Path to the generated report file
    """
    report_path = Path(output_dir) / "processing_report.txt"
    
    with open(report_path, 'w') as f:
        f.write("PDF Schedule Extractor - Batch Processing Report\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Extractions: {results['total_extractions']}\n")
        f.write(f"Successful Saves: {results['successful_saves']}\n")
        f.write(f"Failed Saves: {results['failed_saves']}\n")
        f.write(f"Individual Files Created: {results['individual_files_created']}\n")
        f.write(f"Success Rate: {(results['successful_saves'] / max(results['total_extractions'], 1)) * 100:.1f}%\n\n")
        
        f.write("Equipment Types:\n")
        for equipment_type in results['equipment_types']:
            f.write(f"  - {equipment_type}\n")
        
        f.write("\nCreated Directories:\n")
        for dir_path in results['created_directories']:
            f.write(f"  - {dir_path}\n")
        
        f.write("\nSaved Files:\n")
        for file_path in results['saved_files']:
            f.write(f"  - {file_path}\n")
    
    return str(report_path)

def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        description="PDF Schedule Extractor - Batch Processing Helper"
    )
    parser.add_argument(
        'input_file',
        help='Path to the JSON or ZIP file containing extraction data'
    )
    parser.add_argument(
        '-o', '--output',
        default='extracted_schedules',
        help='Output directory for organized images (default: extracted_schedules)'
    )
    parser.add_argument(
        '-r', '--report',
        action='store_true',
        help='Generate a processing report'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)
    
    # Determine file type and process accordingly
    file_extension = Path(args.input_file).suffix.lower()
    print(f"Processing {args.input_file}...")
    
    if file_extension == '.zip':
        results = process_zip_file(args.input_file, args.output)
    elif file_extension == '.json':
        results = process_extraction_file(args.input_file, args.output)
    else:
        print(f"Error: Unsupported file type '{file_extension}'. Supported types: .json, .zip")
        sys.exit(1)
    
    # Print results
    print(f"\nProcessing Complete!")
    
    if file_extension == '.zip':
        print(f"Total files processed: {results['total_files']}")
        print(f"Files extracted: {results['extracted_files']}")
        print(f"Annotated PDF found: {'Yes' if results['annotated_pdf_found'] else 'No'}")
        if results['annotated_pdf_found']:
            print(f"Annotated PDF: {results['annotated_pdf_path']}")
        print(f"Project data found: {'Yes' if results['project_data_found'] else 'No'}")
        print(f"Equipment types: {', '.join(results['equipment_types']) if results['equipment_types'] else 'Not determined'}")
    else:
        print(f"Total extractions: {results['total_extractions']}")
        print(f"Successful saves: {results['successful_saves']}")
        print(f"Failed saves: {results['failed_saves']}")
        print(f"Individual files created: {results['individual_files_created']}")
        print(f"Equipment types: {', '.join(results['equipment_types'])}")
    
    print(f"Output directory: {args.output}")
    
    if args.verbose:
        print(f"\nCreated directories:")
        for dir_path in results['created_directories']:
            print(f"  - {dir_path}")
    
    # Generate report if requested
    if args.report:
        report_path = create_summary_report(results, args.output)
        print(f"\nReport generated: {report_path}")

if __name__ == "__main__":
    main()