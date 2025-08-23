#!/usr/bin/env python3
"""
Simple Test Extractor for PDF Extractor Coordinates

A minimal version to test coordinate conversion and basic functionality
without requiring all OCR dependencies.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not available")


class SimpleTestExtractor:
    """Basic extractor to test coordinate conversion"""
    
    def __init__(self, pdf_path: str, debug: bool = True):
        self.pdf_path = Path(pdf_path)
        self.debug = debug
        self.page_dimensions = self._get_page_dimensions()
        
        # Setup logging
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
    
    def _get_page_dimensions(self) -> Dict[int, Tuple[float, float]]:
        """Get page dimensions for coordinate conversion"""
        dimensions = {}
        
        if not PYPDF2_AVAILABLE or not self.pdf_path.exists():
            self.logger.warning("Using default page dimensions")
            return {1: (612, 792), 2: (612, 792), 3: (612, 792)}
        
        try:
            with open(self.pdf_path, 'rb') as file:
                reader = PdfReader(file)
                for i, page in enumerate(reader.pages):
                    media_box = page.mediabox
                    width = float(media_box.width)
                    height = float(media_box.height)
                    dimensions[i + 1] = (width, height)
                    
        except Exception as e:
            self.logger.warning(f"Could not read PDF dimensions: {e}")
            dimensions = {1: (612, 792), 2: (612, 792), 3: (612, 792)}
        
        return dimensions
    
    def convert_coordinates(self, coords: Dict) -> Dict:
        """Convert PDF Extractor coordinates to various formats"""
        page_num = coords['page']
        
        if page_num not in self.page_dimensions:
            self.logger.warning(f"Page {page_num} not found, using default dimensions")
            page_width, page_height = (612, 792)
        else:
            page_width, page_height = self.page_dimensions[page_num]
        
        # Original coordinates (top-left origin)
        x, y, width, height = coords['x'], coords['y'], coords['width'], coords['height']
        
        # Convert to bottom-left origin
        top = page_height - y - height
        left = x
        bottom = page_height - y
        right = x + width
        
        # Calculate area and validate
        area_width = right - left
        area_height = bottom - top
        
        conversion_result = {
            'original_coords': coords,
            'page_dimensions': (page_width, page_height),
            'converted_coords': {
                'top': top,
                'left': left, 
                'bottom': bottom,
                'right': right
            },
            'tabula_area': [top, left, bottom, right],
            'area_size': {
                'width': area_width,
                'height': area_height
            },
            'validation': {
                'within_bounds': (0 <= left <= page_width and 
                                0 <= right <= page_width and
                                0 <= top <= page_height and 
                                0 <= bottom <= page_height),
                'positive_area': area_width > 0 and area_height > 0
            }
        }
        
        return conversion_result
    
    def analyze_json_file(self, json_path: str) -> Dict:
        """Analyze the JSON file and test coordinate conversions"""
        
        self.logger.info(f"Analyzing JSON file: {json_path}")
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        analysis = {
            'project_info': {
                'project': data.get('project', 'Unknown'),
                'export_date': data.get('exportDate', 'Unknown'),
                'total_extractions': data.get('totalExtractions', 0),
                'equipment_types': data.get('equipmentTypes', [])
            },
            'extractions': [],
            'coordinate_analysis': {
                'valid_conversions': 0,
                'invalid_conversions': 0,
                'out_of_bounds': 0
            }
        }
        
        # Analyze each extraction
        for equipment_type, extractions in data.get('equipment', {}).items():
            self.logger.info(f"Analyzing {len(extractions)} extractions for {equipment_type}")
            
            for extraction in extractions:
                extraction_name = extraction.get('extractionName', f"extraction_{extraction.get('id', 'unknown')}")
                coords = extraction['coordinates']
                
                # Convert coordinates
                conversion = self.convert_coordinates(coords)
                
                extraction_analysis = {
                    'id': extraction.get('id'),
                    'name': extraction_name,
                    'equipment_type': equipment_type,
                    'extraction_type': extraction.get('extractionType', 'unknown'),
                    'coordinates': coords,
                    'conversion': conversion,
                    'has_ocr_data': 'ocrData' in extraction
                }
                
                # Check if OCR data exists and analyze it
                if 'ocrData' in extraction:
                    ocr_data = extraction['ocrData']
                    extraction_analysis['ocr_info'] = {
                        'success': ocr_data.get('success', False),
                        'provider': ocr_data.get('provider', 'unknown'),
                        'confidence': ocr_data.get('confidence', 0),
                        'has_table_data': 'tableData' in ocr_data,
                        'text_length': len(ocr_data.get('text', ''))
                    }
                
                analysis['extractions'].append(extraction_analysis)
                
                # Update coordinate analysis stats
                if conversion['validation']['within_bounds'] and conversion['validation']['positive_area']:
                    analysis['coordinate_analysis']['valid_conversions'] += 1
                else:
                    analysis['coordinate_analysis']['invalid_conversions'] += 1
                    
                if not conversion['validation']['within_bounds']:
                    analysis['coordinate_analysis']['out_of_bounds'] += 1
                
                # Log details
                self.logger.info(f"  ✓ {extraction_name}")
                self.logger.debug(f"    Original: {coords}")
                self.logger.debug(f"    Converted: {conversion['tabula_area']}")
                self.logger.debug(f"    Valid: {conversion['validation']}")
        
        return analysis
    
    def print_analysis_report(self, analysis: Dict):
        """Print a comprehensive analysis report"""
        
        print(f"\n{'='*60}")
        print(f"PDF EXTRACTOR COORDINATE ANALYSIS")
        print(f"{'='*60}")
        
        # Project info
        info = analysis['project_info']
        print(f"Project: {info['project']}")
        print(f"Export Date: {info['export_date']}")
        print(f"Total Extractions: {info['total_extractions']}")
        print(f"Equipment Types: {', '.join(info['equipment_types'])}")
        
        # Coordinate analysis
        coord_stats = analysis['coordinate_analysis']
        total = coord_stats['valid_conversions'] + coord_stats['invalid_conversions']
        success_rate = (coord_stats['valid_conversions'] / total * 100) if total > 0 else 0
        
        print(f"\n{'='*40}")
        print(f"COORDINATE CONVERSION ANALYSIS")
        print(f"{'='*40}")
        print(f"Valid conversions: {coord_stats['valid_conversions']}/{total} ({success_rate:.1f}%)")
        print(f"Invalid conversions: {coord_stats['invalid_conversions']}")
        print(f"Out of bounds: {coord_stats['out_of_bounds']}")
        
        # Equipment breakdown
        equipment_stats = {}
        for extraction in analysis['extractions']:
            eq_type = extraction['equipment_type']
            if eq_type not in equipment_stats:
                equipment_stats[eq_type] = {'total': 0, 'valid': 0, 'has_ocr': 0}
            
            equipment_stats[eq_type]['total'] += 1
            if extraction['conversion']['validation']['within_bounds']:
                equipment_stats[eq_type]['valid'] += 1
            if extraction['has_ocr_data']:
                equipment_stats[eq_type]['has_ocr'] += 1
        
        print(f"\n{'='*40}")
        print(f"EQUIPMENT TYPE BREAKDOWN")
        print(f"{'='*40}")
        for eq_type, stats in equipment_stats.items():
            print(f"{eq_type}:")
            print(f"  Total: {stats['total']}")
            print(f"  Valid coordinates: {stats['valid']}/{stats['total']}")
            print(f"  Has OCR data: {stats['has_ocr']}/{stats['total']}")
        
        # Individual extraction details
        print(f"\n{'='*40}")
        print(f"EXTRACTION DETAILS")
        print(f"{'='*40}")
        for extraction in analysis['extractions']:
            name = extraction['name']
            coords = extraction['coordinates']
            conversion = extraction['conversion']
            
            print(f"\n{name} ({extraction['equipment_type']}):")
            print(f"  Page: {coords['page']}")
            print(f"  Original coords: ({coords['x']:.1f}, {coords['y']:.1f}, {coords['width']:.1f}, {coords['height']:.1f})")
            print(f"  Tabula area: {[round(x, 1) for x in conversion['tabula_area']]}")
            print(f"  Valid: {conversion['validation']['within_bounds']} | Positive area: {conversion['validation']['positive_area']}")
            
            if extraction['has_ocr_data']:
                ocr = extraction['ocr_info']
                print(f"  OCR: {ocr['provider']} | Success: {ocr['success']} | Confidence: {ocr['confidence']}%")


def main():
    """Test the coordinate conversion with existing data"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test PDF Extractor coordinate conversion')
    parser.add_argument('json_file', help='Path to PDF Extractor JSON file')
    parser.add_argument('--pdf', help='Path to PDF file (optional)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Use PDF if provided, otherwise use dummy path
    pdf_path = args.pdf if args.pdf else "dummy.pdf"
    
    # Initialize extractor
    extractor = SimpleTestExtractor(pdf_path, debug=args.debug)
    
    # Analyze JSON file
    analysis = extractor.analyze_json_file(args.json_file)
    
    # Print report
    extractor.print_analysis_report(analysis)
    
    # Test individual coordinate conversion
    if analysis['extractions']:
        print(f"\n{'='*40}")
        print(f"COORDINATE CONVERSION TEST")
        print(f"{'='*40}")
        
        first_extraction = analysis['extractions'][0]
        coords = first_extraction['coordinates']
        conversion = extractor.convert_coordinates(coords)
        
        print(f"Testing conversion for: {first_extraction['name']}")
        print(f"Page dimensions: {conversion['page_dimensions']}")
        print(f"Original (top-left origin): {coords}")
        print(f"Converted (bottom-left origin): {conversion['converted_coords']}")
        print(f"For tabula-py: {conversion['tabula_area']}")
        print(f"Area size: {conversion['area_size']['width']:.1f} x {conversion['area_size']['height']:.1f}")


if __name__ == '__main__':
    main()