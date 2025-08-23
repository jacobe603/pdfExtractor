#!/usr/bin/env python3
"""
Intelligent Table Extractor for PDF Extractor Coordinates

Uses multiple extraction strategies to reliably extract tables from PDF coordinates.
Supports tabula-py, camelot-py, and pdfplumber with intelligent fallback.

Installation:
pip install tabula-py camelot-py[cv] pdfplumber pandas openpyxl

For camelot requirements:
- cv2: pip install opencv-python
- ghostscript: system package (apt-get install ghostscript on Ubuntu)
"""

import json
import pandas as pd
import os
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum

# Import extraction libraries with graceful fallbacks
try:
    import tabula
    TABULA_AVAILABLE = True
except ImportError:
    TABULA_AVAILABLE = False
    print("Warning: tabula-py not available. Install with: pip install tabula-py")

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    print("Warning: camelot-py not available. Install with: pip install camelot-py[cv]")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("Warning: pdfplumber not available. Install with: pip install pdfplumber")

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not available. Install with: pip install PyPDF2")


class ExtractionMethod(Enum):
    """Available extraction methods"""
    TABULA_LATTICE = "tabula_lattice"
    TABULA_STREAM = "tabula_stream" 
    CAMELOT_LATTICE = "camelot_lattice"
    CAMELOT_STREAM = "camelot_stream"
    PDFPLUMBER = "pdfplumber"
    HYBRID = "hybrid"


@dataclass
class ExtractionResult:
    """Result of a table extraction attempt"""
    method: str
    success: bool
    tables: List[pd.DataFrame]
    confidence: float
    error: Optional[str] = None
    metadata: Optional[Dict] = None


class IntelligentTableExtractor:
    """Multi-strategy table extractor optimized for construction schedules"""
    
    def __init__(self, pdf_path: str, debug: bool = False):
        """
        Initialize extractor with PDF file
        
        Args:
            pdf_path: Path to PDF file
            debug: Enable debug logging
        """
        self.pdf_path = Path(pdf_path)
        self.debug = debug
        self.page_dimensions = self._get_page_dimensions()
        
        # Setup logging
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Validate available libraries
        self._validate_dependencies()
    
    def _validate_dependencies(self):
        """Check which extraction libraries are available"""
        available = []
        if TABULA_AVAILABLE:
            available.append("tabula-py")
        if CAMELOT_AVAILABLE:
            available.append("camelot-py")
        if PDFPLUMBER_AVAILABLE:
            available.append("pdfplumber")
            
        if not available:
            raise ImportError("No table extraction libraries available. Install tabula-py, camelot-py, or pdfplumber")
        
        self.logger.info(f"Available extraction libraries: {', '.join(available)}")
    
    def _get_page_dimensions(self) -> Dict[int, Tuple[float, float]]:
        """Get page dimensions for coordinate conversion"""
        dimensions = {}
        
        if not PYPDF2_AVAILABLE:
            # Default letter size fallback
            self.logger.warning("PyPDF2 not available, using default page size")
            return {1: (612, 792)}
        
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
            dimensions = {1: (612, 792)}
        
        return dimensions
    
    def _convert_coordinates(self, coords: Dict) -> Tuple[List[float], Dict]:
        """Convert PDF Extractor coordinates to various formats"""
        page_num = coords['page']
        
        if page_num not in self.page_dimensions:
            raise ValueError(f"Page {page_num} not found in PDF")
        
        page_width, page_height = self.page_dimensions[page_num]
        
        # Original coordinates (top-left origin)
        x, y, width, height = coords['x'], coords['y'], coords['width'], coords['height']
        
        # Convert to bottom-left origin for tabula/camelot
        top = page_height - y - height
        left = x
        bottom = page_height - y  
        right = x + width
        
        # Different format requirements
        formats = {
            'tabula_area': [top, left, bottom, right],
            'camelot_area': f"{left},{top},{right},{bottom}",
            'pdfplumber_bbox': (left, top, right, bottom),
            'original': coords
        }
        
        return formats['tabula_area'], formats
    
    def extract_with_tabula(self, coords: Dict, method: str = "lattice") -> ExtractionResult:
        """Extract table using tabula-py"""
        if not TABULA_AVAILABLE:
            return ExtractionResult("tabula", False, [], 0.0, "tabula-py not available")
        
        try:
            area, formats = self._convert_coordinates(coords)
            page_num = coords['page']
            
            # Configure extraction parameters
            if method == "lattice":
                kwargs = {
                    'lattice': True,
                    'stream': False,
                    'pandas_options': {'header': 0}
                }
            else:  # stream
                kwargs = {
                    'lattice': False, 
                    'stream': True,
                    'pandas_options': {'header': 0}
                }
            
            # Common parameters
            kwargs.update({
                'pages': [page_num],
                'area': area,
                'multiple_tables': False,
                'silent': True
            })
            
            tables = tabula.read_pdf(str(self.pdf_path), **kwargs)
            
            if tables and len(tables) > 0:
                # Filter out empty tables
                valid_tables = [df for df in tables if not df.empty and df.shape[0] > 0]
                if valid_tables:
                    confidence = self._calculate_confidence(valid_tables[0])
                    return ExtractionResult(
                        f"tabula_{method}", True, valid_tables, confidence,
                        metadata={'area': area, 'method': method}
                    )
            
            return ExtractionResult(f"tabula_{method}", False, [], 0.0, "No valid tables found")
            
        except Exception as e:
            return ExtractionResult(f"tabula_{method}", False, [], 0.0, str(e))
    
    def extract_with_camelot(self, coords: Dict, method: str = "lattice") -> ExtractionResult:
        """Extract table using camelot-py"""
        if not CAMELOT_AVAILABLE:
            return ExtractionResult("camelot", False, [], 0.0, "camelot-py not available")
        
        try:
            _, formats = self._convert_coordinates(coords)
            page_num = coords['page']
            
            # Configure extraction parameters
            kwargs = {
                'pages': str(page_num),
                'table_areas': [formats['camelot_area']],
                'flavor': method  # 'lattice' or 'stream'
            }
            
            if method == 'lattice':
                kwargs.update({
                    'line_scale': 15,
                    'copy_text': ['v'],
                    'shift_text': ['']
                })
            else:  # stream
                kwargs.update({
                    'columns': None,
                    'edge_tol': 50
                })
            
            tables = camelot.read_pdf(str(self.pdf_path), **kwargs)
            
            if tables and len(tables) > 0:
                valid_tables = []
                total_confidence = 0
                
                for table in tables:
                    if hasattr(table, 'df') and not table.df.empty:
                        valid_tables.append(table.df)
                        # Camelot provides accuracy score
                        if hasattr(table, 'accuracy'):
                            total_confidence += table.accuracy
                
                if valid_tables:
                    avg_confidence = total_confidence / len(valid_tables) if len(valid_tables) > 0 else 0
                    return ExtractionResult(
                        f"camelot_{method}", True, valid_tables, avg_confidence,
                        metadata={'area': formats['camelot_area'], 'method': method}
                    )
            
            return ExtractionResult(f"camelot_{method}", False, [], 0.0, "No valid tables found")
            
        except Exception as e:
            return ExtractionResult(f"camelot_{method}", False, [], 0.0, str(e))
    
    def extract_with_pdfplumber(self, coords: Dict) -> ExtractionResult:
        """Extract table using pdfplumber"""
        if not PDFPLUMBER_AVAILABLE:
            return ExtractionResult("pdfplumber", False, [], 0.0, "pdfplumber not available")
        
        try:
            _, formats = self._convert_coordinates(coords)
            page_num = coords['page']
            bbox = formats['pdfplumber_bbox']
            
            with pdfplumber.open(self.pdf_path) as pdf:
                if page_num > len(pdf.pages):
                    return ExtractionResult("pdfplumber", False, [], 0.0, f"Page {page_num} not found")
                
                page = pdf.pages[page_num - 1]  # pdfplumber uses 0-based indexing
                
                # Crop page to bounding box
                cropped = page.crop(bbox)
                
                # Extract table with various strategies
                tables = []
                
                # Strategy 1: Default table extraction
                try:
                    table_data = cropped.extract_table()
                    if table_data:
                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                        tables.append(df)
                except:
                    pass
                
                # Strategy 2: Extract tables (multiple)
                try:
                    table_list = cropped.extract_tables()
                    for table_data in table_list:
                        if table_data and len(table_data) > 1:
                            df = pd.DataFrame(table_data[1:], columns=table_data[0])
                            tables.append(df)
                except:
                    pass
                
                # Strategy 3: Custom table settings
                try:
                    table_settings = {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 3
                    }
                    table_data = cropped.extract_table(table_settings)
                    if table_data:
                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                        tables.append(df)
                except:
                    pass
                
                # Remove duplicates and empty tables
                valid_tables = []
                for df in tables:
                    if not df.empty and df.shape[0] > 0:
                        # Remove tables that are too similar (duplicates)
                        is_duplicate = False
                        for existing_df in valid_tables:
                            if df.shape == existing_df.shape and df.equals(existing_df):
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            valid_tables.append(df)
                
                if valid_tables:
                    confidence = self._calculate_confidence(valid_tables[0])
                    return ExtractionResult(
                        "pdfplumber", True, valid_tables, confidence,
                        metadata={'bbox': bbox}
                    )
            
            return ExtractionResult("pdfplumber", False, [], 0.0, "No valid tables found")
            
        except Exception as e:
            return ExtractionResult("pdfplumber", False, [], 0.0, str(e))
    
    def _calculate_confidence(self, df: pd.DataFrame) -> float:
        """Calculate confidence score for extracted table"""
        if df.empty:
            return 0.0
        
        score = 0.0
        total_cells = df.shape[0] * df.shape[1]
        
        # Factor 1: Non-null cell ratio (0-40 points)
        non_null_ratio = df.count().sum() / total_cells
        score += non_null_ratio * 40
        
        # Factor 2: Consistent column structure (0-30 points)
        col_consistency = 1.0 - (df.isnull().sum().std() / df.shape[0])
        score += max(0, col_consistency) * 30
        
        # Factor 3: Table size reasonableness (0-20 points)
        if 2 <= df.shape[1] <= 15 and 1 <= df.shape[0] <= 100:
            score += 20
        elif df.shape[1] >= 2 and df.shape[0] >= 1:
            score += 10
        
        # Factor 4: Data type consistency (0-10 points)
        numeric_cols = 0
        for col in df.columns:
            try:
                pd.to_numeric(df[col], errors='coerce')
                numeric_cols += 1
            except:
                pass
        
        if numeric_cols > 0:
            score += min(10, numeric_cols * 2)
        
        return min(100.0, score)
    
    def extract_table_intelligent(self, coords: Dict) -> ExtractionResult:
        """Extract table using intelligent method selection"""
        
        self.logger.info(f"Extracting table from page {coords['page']} at coordinates {coords}")
        
        # Define extraction strategies in order of preference
        strategies = []
        
        if CAMELOT_AVAILABLE:
            strategies.extend([
                (self.extract_with_camelot, {"method": "lattice"}),
                (self.extract_with_camelot, {"method": "stream"})
            ])
        
        if TABULA_AVAILABLE:
            strategies.extend([
                (self.extract_with_tabula, {"method": "lattice"}),
                (self.extract_with_tabula, {"method": "stream"})
            ])
        
        if PDFPLUMBER_AVAILABLE:
            strategies.append((self.extract_with_pdfplumber, {}))
        
        best_result = ExtractionResult("none", False, [], 0.0, "No extraction methods available")
        
        for strategy_func, kwargs in strategies:
            result = strategy_func(coords, **kwargs)
            
            self.logger.debug(f"Method {result.method}: success={result.success}, confidence={result.confidence:.1f}")
            
            if result.success and result.confidence > best_result.confidence:
                best_result = result
                
                # If we get a high-confidence result, use it
                if result.confidence >= 70:
                    break
        
        return best_result
    
    def process_extraction_json(self, json_path: str, output_dir: Optional[str] = None) -> Dict:
        """Process entire PDF Extractor JSON file"""
        
        self.logger.info(f"Processing JSON file: {json_path}")
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        results = {
            'successful_extractions': [],
            'failed_extractions': [],
            'total_processed': 0,
            'extraction_summary': {}
        }
        
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Process each equipment type
        for equipment_type, extractions in data.get('equipment', {}).items():
            self.logger.info(f"Processing {len(extractions)} extractions for {equipment_type}")
            
            for extraction in extractions:
                results['total_processed'] += 1
                
                extraction_name = extraction.get('extractionName', f"extraction_{extraction.get('id', 'unknown')}")
                coords = extraction['coordinates']
                
                try:
                    # Extract table using intelligent method
                    result = self.extract_table_intelligent(coords)
                    
                    if result.success and result.tables:
                        # Prepare result data
                        extraction_result = {
                            'extraction_id': extraction.get('id'),
                            'name': extraction_name,
                            'equipment_type': equipment_type,
                            'extraction_type': extraction.get('extractionType', 'unknown'),
                            'page': coords['page'],
                            'coordinates': coords,
                            'method_used': result.method,
                            'confidence': result.confidence,
                            'table_count': len(result.tables),
                            'tables': result.tables
                        }
                        
                        # Save tables to files if output directory specified
                        if output_dir:
                            saved_files = self._save_extraction_files(
                                extraction_result, output_path
                            )
                            extraction_result['saved_files'] = saved_files
                        
                        results['successful_extractions'].append(extraction_result)
                        self.logger.info(f"✓ {extraction_name}: {len(result.tables)} table(s) using {result.method} (confidence: {result.confidence:.1f})")
                        
                    else:
                        error_msg = result.error or "No tables extracted"
                        results['failed_extractions'].append({
                            'extraction_id': extraction.get('id'),
                            'name': extraction_name,
                            'equipment_type': equipment_type,
                            'error': error_msg
                        })
                        self.logger.warning(f"✗ {extraction_name}: {error_msg}")
                        
                except Exception as e:
                    results['failed_extractions'].append({
                        'extraction_id': extraction.get('id', 'unknown'),
                        'name': extraction_name,
                        'equipment_type': equipment_type,
                        'error': str(e)
                    })
                    self.logger.error(f"✗ Error processing {extraction_name}: {e}")
        
        # Generate summary
        total = results['total_processed']
        successful = len(results['successful_extractions'])
        failed = len(results['failed_extractions'])
        
        results['extraction_summary'] = {
            'total_processed': total,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total * 100) if total > 0 else 0
        }
        
        self.logger.info(f"Extraction complete: {successful}/{total} successful ({results['extraction_summary']['success_rate']:.1f}%)")
        
        return results
    
    def _save_extraction_files(self, extraction_result: Dict, output_dir: Path) -> Dict:
        """Save extracted tables to various formats"""
        saved_files = {}
        
        equipment_type = extraction_result['equipment_type']
        name = extraction_result['name']
        page = extraction_result['page']
        
        # Create equipment subdirectory
        eq_dir = output_dir / equipment_type
        eq_dir.mkdir(exist_ok=True)
        
        # Clean filename
        clean_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_name = clean_name.replace(' ', '_')
        
        base_filename = f"{clean_name}_page{page}"
        
        # Save tables in multiple formats
        for i, df in enumerate(extraction_result['tables']):
            table_suffix = f"_table{i+1}" if len(extraction_result['tables']) > 1 else ""
            
            # CSV format
            csv_file = eq_dir / f"{base_filename}{table_suffix}.csv"
            df.to_csv(csv_file, index=False)
            saved_files[f'csv_table_{i+1}'] = str(csv_file)
            
            # Excel format
            excel_file = eq_dir / f"{base_filename}{table_suffix}.xlsx"
            df.to_excel(excel_file, index=False)
            saved_files[f'excel_table_{i+1}'] = str(excel_file)
            
            # JSON format (for API compatibility)
            json_file = eq_dir / f"{base_filename}{table_suffix}_data.json"
            table_json = {
                'extraction_info': {
                    'name': name,
                    'equipment_type': equipment_type,
                    'page': page,
                    'method': extraction_result['method_used'],
                    'confidence': extraction_result['confidence']
                },
                'table_data': {
                    'rows': len(df),
                    'columns': len(df.columns),
                    'headers': list(df.columns),
                    'data': df.values.tolist()
                }
            }
            
            with open(json_file, 'w') as f:
                json.dump(table_json, f, indent=2)
            saved_files[f'json_table_{i+1}'] = str(json_file)
        
        return saved_files


def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Intelligent Table Extractor for PDF Extractor coordinates')
    parser.add_argument('pdf_file', help='Path to PDF file')
    parser.add_argument('json_file', help='Path to PDF Extractor JSON file')
    parser.add_argument('-o', '--output', help='Output directory for extracted tables', default='extracted_tables')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--method', choices=['auto', 'tabula', 'camelot', 'pdfplumber'], 
                        default='auto', help='Extraction method preference')
    
    args = parser.parse_args()
    
    # Initialize extractor
    extractor = IntelligentTableExtractor(args.pdf_file, debug=args.debug)
    
    # Process JSON file
    results = extractor.process_extraction_json(args.json_file, args.output)
    
    # Print summary
    summary = results['extraction_summary']
    print(f"\n{'='*50}")
    print(f"EXTRACTION SUMMARY")
    print(f"{'='*50}")
    print(f"Total processed: {summary['total_processed']}")
    print(f"Successful: {summary['successful']} ({summary['success_rate']:.1f}%)")
    print(f"Failed: {summary['failed']}")
    
    if results['successful_extractions']:
        print(f"\nSuccessful extractions saved to: {args.output}")
        
        # Show method distribution
        methods = {}
        for extraction in results['successful_extractions']:
            method = extraction['method_used']
            methods[method] = methods.get(method, 0) + 1
        
        print(f"\nMethods used:")
        for method, count in methods.items():
            print(f"  {method}: {count}")
    
    if results['failed_extractions']:
        print(f"\nFailed extractions:")
        for failure in results['failed_extractions']:
            print(f"  - {failure['name']}: {failure['error']}")


if __name__ == '__main__':
    main()