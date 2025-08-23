#!/usr/bin/env python3
"""
Working Test Extractor for PDF Extractor Coordinates

Tests actual table extraction using pdfplumber with your coordinate data.
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("Error: pdfplumber not available")

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False


class WorkingTestExtractor:
    """Test extractor using pdfplumber for actual table extraction"""
    
    def __init__(self, pdf_path: str, debug: bool = True):
        self.pdf_path = Path(pdf_path)
        self.debug = debug
        self.page_dimensions = self._get_page_dimensions()
        
        # Setup logging
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
        
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber is required")
    
    def _get_page_dimensions(self) -> Dict[int, Tuple[float, float]]:
        """Get page dimensions"""
        dimensions = {}
        
        if not self.pdf_path.exists():
            self.logger.warning(f"PDF file not found: {self.pdf_path}")
            return {1: (612, 792), 2: (612, 792)}
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    dimensions[i + 1] = (page.width, page.height)
        except Exception as e:
            self.logger.warning(f"Could not read PDF with pdfplumber: {e}")
            # Fallback to PyPDF2
            if PYPDF2_AVAILABLE:
                try:
                    with open(self.pdf_path, 'rb') as file:
                        reader = PdfReader(file)
                        for i, page in enumerate(reader.pages):
                            media_box = page.mediabox
                            width = float(media_box.width)
                            height = float(media_box.height)
                            dimensions[i + 1] = (width, height)
                except Exception as e2:
                    self.logger.warning(f"PyPDF2 also failed: {e2}")
                    dimensions = {1: (612, 792), 2: (612, 792)}
        
        return dimensions
    
    def convert_coordinates(self, coords: Dict) -> Dict:
        """Convert coordinates and return conversion info"""
        page_num = coords['page']
        
        if page_num not in self.page_dimensions:
            self.logger.warning(f"Page {page_num} not found")
            page_width, page_height = (612, 792)
        else:
            page_width, page_height = self.page_dimensions[page_num]
        
        # Original coordinates (top-left origin)
        x, y, width, height = coords['x'], coords['y'], coords['width'], coords['height']
        
        # For pdfplumber, coordinates are (left, top, right, bottom) with top-left origin
        # So we can use the original coordinates directly!
        left = x
        top = y
        right = x + width
        bottom = y + height
        
        return {
            'original_coords': coords,
            'page_dimensions': (page_width, page_height),
            'pdfplumber_bbox': (left, top, right, bottom),
            'area_size': {'width': width, 'height': height},
            'validation': {
                'within_bounds': (0 <= left <= page_width and 
                                0 <= right <= page_width and
                                0 <= top <= page_height and 
                                0 <= bottom <= page_height),
                'positive_area': width > 0 and height > 0
            }
        }
    
    def extract_table_with_pdfplumber(self, coords: Dict) -> Dict:
        """Extract table using pdfplumber"""
        page_num = coords['page']
        conversion = self.convert_coordinates(coords)
        bbox = conversion['pdfplumber_bbox']
        
        result = {
            'success': False,
            'method': 'pdfplumber',
            'tables': [],
            'raw_text': '',
            'error': None,
            'metadata': conversion
        }
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                if page_num > len(pdf.pages):
                    result['error'] = f"Page {page_num} not found in PDF"
                    return result
                
                page = pdf.pages[page_num - 1]  # 0-based indexing
                
                # Crop page to the specified area
                cropped = page.crop(bbox)
                
                # Extract raw text for analysis
                raw_text = cropped.extract_text()
                result['raw_text'] = raw_text or ''
                
                # Try multiple table extraction strategies
                tables = []
                
                # Strategy 1: Default table extraction
                try:
                    table_data = cropped.extract_table()
                    if table_data and len(table_data) > 1:
                        # Convert to DataFrame
                        headers = table_data[0] if table_data[0] else [f'Col_{i}' for i in range(len(table_data[1]))]
                        data_rows = table_data[1:]
                        
                        # Clean headers
                        headers = [str(h).strip() if h else f'Col_{i}' for i, h in enumerate(headers)]
                        
                        # Create DataFrame
                        df = pd.DataFrame(data_rows, columns=headers)
                        
                        # Clean data - remove completely empty rows
                        df = df.dropna(how='all')
                        
                        if not df.empty:
                            tables.append(df)
                            
                except Exception as e:
                    self.logger.debug(f"Strategy 1 failed: {e}")
                
                # Strategy 2: Multiple tables
                try:
                    tables_list = cropped.extract_tables()
                    for table_data in tables_list:
                        if table_data and len(table_data) > 1:
                            headers = table_data[0] if table_data[0] else [f'Col_{i}' for i in range(len(table_data[1]))]
                            data_rows = table_data[1:]
                            
                            headers = [str(h).strip() if h else f'Col_{i}' for i, h in enumerate(headers)]
                            df = pd.DataFrame(data_rows, columns=headers)
                            df = df.dropna(how='all')
                            
                            if not df.empty:
                                # Check if this is a duplicate
                                is_duplicate = False
                                for existing_df in tables:
                                    if df.shape == existing_df.shape and df.equals(existing_df):
                                        is_duplicate = True
                                        break
                                
                                if not is_duplicate:
                                    tables.append(df)
                                    
                except Exception as e:
                    self.logger.debug(f"Strategy 2 failed: {e}")
                
                # Strategy 3: Custom table settings for construction schedules
                try:
                    table_settings = {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines", 
                        "intersection_tolerance": 5,
                        "snap_tolerance": 3,
                        "join_tolerance": 3
                    }
                    
                    table_data = cropped.extract_table(table_settings)
                    if table_data and len(table_data) > 1:
                        headers = table_data[0] if table_data[0] else [f'Col_{i}' for i in range(len(table_data[1]))]
                        data_rows = table_data[1:]
                        
                        headers = [str(h).strip() if h else f'Col_{i}' for i, h in enumerate(headers)]
                        df = pd.DataFrame(data_rows, columns=headers)
                        df = df.dropna(how='all')
                        
                        if not df.empty:
                            # Check for duplicates
                            is_duplicate = False
                            for existing_df in tables:
                                if df.shape == existing_df.shape and df.equals(existing_df):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                tables.append(df)
                                
                except Exception as e:
                    self.logger.debug(f"Strategy 3 failed: {e}")
                
                # Return results
                if tables:
                    result['success'] = True
                    result['tables'] = tables
                    
                    # Calculate basic confidence score
                    best_table = max(tables, key=lambda df: df.shape[0] * df.shape[1])
                    total_cells = best_table.shape[0] * best_table.shape[1]
                    non_empty_cells = best_table.count().sum()
                    confidence = (non_empty_cells / total_cells * 100) if total_cells > 0 else 0
                    result['confidence'] = confidence
                    
                else:
                    result['error'] = "No tables found in the specified area"
                    
                # Also check what kind of content we found
                result['content_analysis'] = {
                    'has_text': bool(raw_text and raw_text.strip()),
                    'text_length': len(raw_text) if raw_text else 0,
                    'line_count': len(raw_text.split('\n')) if raw_text else 0,
                    'likely_table': bool(raw_text and any(char in raw_text for char in ['\t', '  ', '|']))
                }
                
        except Exception as e:
            result['error'] = str(e)
            
        return result
    
    def test_extraction_from_json(self, json_path: str) -> Dict:
        """Test extraction for all coordinates in JSON file"""
        
        self.logger.info(f"Testing extraction from: {json_path}")
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        results = {
            'project_info': {
                'project': data.get('project', 'Unknown'),
                'total_extractions': data.get('totalExtractions', 0)
            },
            'extraction_tests': [],
            'summary': {
                'total_tested': 0,
                'successful': 0,
                'failed': 0,
                'has_text': 0,
                'has_tables': 0
            }
        }
        
        # Test each extraction
        for equipment_type, extractions in data.get('equipment', {}).items():
            for extraction in extractions:
                results['summary']['total_tested'] += 1
                
                extraction_name = extraction.get('extractionName', f"extraction_{extraction.get('id', 'unknown')}")
                coords = extraction['coordinates']
                
                self.logger.info(f"Testing: {extraction_name}")
                
                # Extract table
                extraction_result = self.extract_table_with_pdfplumber(coords)
                
                test_result = {
                    'name': extraction_name,
                    'equipment_type': equipment_type,
                    'extraction_type': extraction.get('extractionType', 'unknown'),
                    'coordinates': coords,
                    'extraction_result': extraction_result,
                    'existing_ocr': extraction.get('ocrData', {})
                }
                
                results['extraction_tests'].append(test_result)
                
                # Update summary
                if extraction_result['success']:
                    results['summary']['successful'] += 1
                else:
                    results['summary']['failed'] += 1
                
                if extraction_result['content_analysis']['has_text']:
                    results['summary']['has_text'] += 1
                
                if extraction_result['tables']:
                    results['summary']['has_tables'] += 1
                
                # Log result
                if extraction_result['success']:
                    table_count = len(extraction_result['tables'])
                    confidence = extraction_result.get('confidence', 0)
                    self.logger.info(f"  ✓ Found {table_count} table(s), confidence: {confidence:.1f}%")
                else:
                    self.logger.warning(f"  ✗ {extraction_result['error']}")
        
        return results
    
    def print_test_report(self, results: Dict):
        """Print comprehensive test report"""
        
        print(f"\n{'='*60}")
        print(f"TABLE EXTRACTION TEST REPORT")
        print(f"{'='*60}")
        
        # Project info
        info = results['project_info']
        print(f"Project: {info['project']}")
        print(f"Total Extractions: {info['total_extractions']}")
        
        # Summary
        summary = results['summary']
        success_rate = (summary['successful'] / summary['total_tested'] * 100) if summary['total_tested'] > 0 else 0
        
        print(f"\n{'='*40}")
        print(f"EXTRACTION SUMMARY")
        print(f"{'='*40}")
        print(f"Total tested: {summary['total_tested']}")
        print(f"Successful: {summary['successful']} ({success_rate:.1f}%)")
        print(f"Failed: {summary['failed']}")
        print(f"Areas with text: {summary['has_text']}")
        print(f"Areas with tables: {summary['has_tables']}")
        
        # Individual results
        print(f"\n{'='*40}")
        print(f"DETAILED RESULTS")
        print(f"{'='*40}")
        
        for test in results['extraction_tests']:
            name = test['name']
            coords = test['coordinates']
            result = test['extraction_result']
            
            print(f"\n{name} ({test['equipment_type']}):")
            print(f"  Page: {coords['page']}")
            print(f"  Area: {coords['width']:.0f} x {coords['height']:.0f} at ({coords['x']:.0f}, {coords['y']:.0f})")
            
            if result['success']:
                print(f"  ✓ Success: {len(result['tables'])} table(s)")
                print(f"  Confidence: {result.get('confidence', 0):.1f}%")
                
                # Show table info
                for i, df in enumerate(result['tables']):
                    print(f"    Table {i+1}: {df.shape[0]} rows x {df.shape[1]} columns")
                    print(f"    Headers: {list(df.columns)}")
            else:
                print(f"  ✗ Failed: {result['error']}")
            
            # Content analysis
            content = result['content_analysis']
            print(f"  Text found: {content['has_text']} ({content['text_length']} chars)")
            print(f"  Likely table content: {content['likely_table']}")
            
            # Compare with existing OCR if available
            existing_ocr = test['existing_ocr']
            if existing_ocr:
                ocr_success = existing_ocr.get('success', False)
                ocr_provider = existing_ocr.get('provider', 'unknown')
                ocr_confidence = existing_ocr.get('confidence', 0)
                print(f"  Existing OCR: {ocr_provider} | Success: {ocr_success} | Confidence: {ocr_confidence}%")


def main():
    """Test extraction with your data"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test table extraction with PDF Extractor coordinates')
    parser.add_argument('json_file', help='Path to PDF Extractor JSON file')
    parser.add_argument('pdf_file', help='Path to PDF file')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Initialize extractor
    extractor = WorkingTestExtractor(args.pdf_file, debug=args.debug)
    
    # Test extraction
    results = extractor.test_extraction_from_json(args.json_file)
    
    # Print report
    extractor.print_test_report(results)
    
    # Save first successful table as example
    for test in results['extraction_tests']:
        if test['extraction_result']['success'] and test['extraction_result']['tables']:
            df = test['extraction_result']['tables'][0]
            output_file = f"test_extraction_{test['name'].replace(' ', '_')}.csv"
            df.to_csv(output_file, index=False)
            print(f"\nSaved example table to: {output_file}")
            break


if __name__ == '__main__':
    main()