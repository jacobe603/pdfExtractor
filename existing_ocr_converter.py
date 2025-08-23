#!/usr/bin/env python3
"""
Existing OCR Data Converter for PDF Extractor

Converts high-quality OCR data already stored in the JSON file into 
structured tables and various export formats. No re-processing needed!
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
from dataclasses import dataclass
import re

@dataclass
class OCRExtractionResult:
    """Result of converting existing OCR data"""
    success: bool
    extraction_name: str
    equipment_type: str
    provider: str
    confidence: float
    tables: List[pd.DataFrame]
    raw_text: str
    notes: List[str]
    metadata: Dict
    error: Optional[str] = None


class ExistingOCRConverter:
    """Converts existing high-quality OCR data to structured tables"""
    
    def __init__(self, debug: bool = True):
        self.debug = debug
        
        # Setup logging
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
    
    def parse_ocr_data(self, extraction: Dict) -> OCRExtractionResult:
        """Parse existing OCR data from extraction"""
        
        extraction_name = extraction.get('extractionName', 'Unknown')
        equipment_type = extraction.get('equipmentType', extraction.get('type', 'Unknown'))
        
        # Check if OCR data exists
        if 'ocrData' not in extraction:
            return OCRExtractionResult(
                success=False,
                extraction_name=extraction_name,
                equipment_type=equipment_type,
                provider='none',
                confidence=0.0,
                tables=[],
                raw_text='',
                notes=[],
                metadata={},
                error='No OCR data found'
            )
        
        ocr_data = extraction['ocrData']
        
        # Extract basic OCR info
        provider = ocr_data.get('provider', 'Unknown')
        confidence = ocr_data.get('confidence', 0)
        raw_text = ocr_data.get('text', '')
        
        tables = []
        notes = []
        
        try:
            # Handle structured table data (new format)
            if 'tableData' in ocr_data and ocr_data['tableData'].get('isTable', False):
                table_info = ocr_data['tableData']['tableData']
                
                headers = table_info.get('headers', [])
                data_rows = table_info.get('data', [])
                
                if headers and data_rows:
                    # Create DataFrame
                    df = pd.DataFrame(data_rows, columns=headers)
                    
                    # Clean the data
                    df = self._clean_dataframe(df)
                    
                    if not df.empty:
                        tables.append(df)
                        self.logger.debug(f"Parsed structured table: {df.shape[0]} rows x {df.shape[1]} cols")
            
            # Handle legacy format or text-only OCR
            elif raw_text:
                # Try to parse table from raw text
                parsed_df = self._parse_text_to_table(raw_text)
                if parsed_df is not None and not parsed_df.empty:
                    tables.append(parsed_df)
                    self.logger.debug(f"Parsed text table: {parsed_df.shape[0]} rows x {parsed_df.shape[1]} cols")
            
            # Extract notes/footnotes
            notes = self._extract_notes_from_text(raw_text)
            
            # Handle notes object (new format)
            if 'notes' in ocr_data and isinstance(ocr_data['notes'], dict):
                note_entries = ocr_data['notes'].get('entries', [])
                if note_entries:
                    notes.extend(note_entries)
            
            # Prepare metadata
            metadata = {
                'coordinates': extraction.get('coordinates', {}),
                'extraction_type': extraction.get('extractionType', 'unknown'),
                'ocr_provider': provider,
                'ocr_confidence': confidence,
                'has_structured_data': 'tableData' in ocr_data,
                'table_count': len(tables),
                'notes_count': len(notes)
            }
            
            return OCRExtractionResult(
                success=len(tables) > 0,
                extraction_name=extraction_name,
                equipment_type=equipment_type,
                provider=provider,
                confidence=confidence,
                tables=tables,
                raw_text=raw_text,
                notes=notes,
                metadata=metadata
            )
            
        except Exception as e:
            return OCRExtractionResult(
                success=False,
                extraction_name=extraction_name,
                equipment_type=equipment_type,
                provider=provider,
                confidence=confidence,
                tables=[],
                raw_text=raw_text,
                notes=[],
                metadata={},
                error=str(e)
            )
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and optimize DataFrame"""
        
        # Remove completely empty rows and columns
        df = df.dropna(how='all').loc[:, df.notna().any()]
        
        # Clean string data
        for col in df.columns:
            if df[col].dtype == 'object':
                # Strip whitespace
                df[col] = df[col].astype(str).str.strip()
                
                # Replace empty strings with NaN
                df[col] = df[col].replace('', pd.NA)
                
                # Handle common OCR artifacts
                df[col] = df[col].str.replace(r'[^\w\s\.,\-\(\)\/]', '', regex=True)
        
        # Try to convert numeric columns
        for col in df.columns:
            if df[col].dtype == 'object':
                # Check if column looks numeric
                sample_values = df[col].dropna().head(5)
                if sample_values.empty:
                    continue
                
                # Look for numeric patterns
                numeric_pattern = r'^[\d,\.\-\s]+$'
                if sample_values.astype(str).str.match(numeric_pattern).all():
                    try:
                        # Clean numeric strings (remove commas, extra spaces)
                        cleaned = df[col].astype(str).str.replace(',', '').str.strip()
                        df[col] = pd.to_numeric(cleaned, errors='ignore')
                    except:
                        pass
        
        return df
    
    def _parse_text_to_table(self, text: str) -> Optional[pd.DataFrame]:
        """Parse raw OCR text into table format"""
        
        if not text or not text.strip():
            return None
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if len(lines) < 2:
            return None
        
        # Try to identify table structure
        table_lines = []
        
        for line in lines:
            # Skip lines that look like titles or notes
            if (line.isupper() and len(line.split()) <= 4) or line.startswith('1)'):
                continue
            
            # Split on multiple spaces or tabs
            row = re.split(r'\s{2,}|\t', line)
            row = [cell.strip() for cell in row if cell.strip()]
            
            if len(row) >= 2:
                table_lines.append(row)
        
        if len(table_lines) < 2:
            return None
        
        try:
            # Use first valid line as headers
            headers = table_lines[0]
            data_rows = table_lines[1:]
            
            # Ensure consistent column count
            max_cols = max(len(row) for row in data_rows) if data_rows else len(headers)
            
            # Normalize row lengths
            normalized_data = []
            for row in data_rows:
                padded_row = row + [''] * (max_cols - len(row))
                normalized_data.append(padded_row[:max_cols])
            
            # Normalize headers
            padded_headers = headers + [f'Column_{i}' for i in range(len(headers), max_cols)]
            padded_headers = padded_headers[:max_cols]
            
            df = pd.DataFrame(normalized_data, columns=padded_headers)
            return self._clean_dataframe(df)
            
        except Exception as e:
            self.logger.warning(f"Text table parsing failed: {e}")
            return None
    
    def _extract_notes_from_text(self, text: str) -> List[str]:
        """Extract numbered notes/footnotes from text"""
        
        if not text:
            return []
        
        notes = []
        
        # Look for numbered notes (1), 2), etc.)
        note_pattern = r'(\d+\)\s*.+?)(?=\d+\)|$)'
        matches = re.findall(note_pattern, text, re.DOTALL)
        
        for match in matches:
            # Clean up the note text
            note_text = re.sub(r'\s+', ' ', match.strip())
            if note_text:
                notes.append(note_text)
        
        return notes
    
    def convert_json_file(self, json_path: str, output_dir: Optional[str] = None) -> Dict:
        """Convert all OCR data in JSON file to structured tables"""
        
        self.logger.info(f"Converting existing OCR data from: {json_path}")
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        results = {
            'project_info': {
                'project': data.get('project', 'Unknown'),
                'export_date': data.get('exportDate', 'Unknown'),
                'total_extractions': data.get('totalExtractions', 0)
            },
            'conversions': [],
            'summary': {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'total_tables': 0,
                'total_notes': 0,
                'providers': {}
            }
        }
        
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Process each extraction
        for equipment_type, extractions in data.get('equipment', {}).items():
            self.logger.info(f"Processing {len(extractions)} extractions for {equipment_type}")
            
            for extraction in extractions:
                results['summary']['total_processed'] += 1
                
                # Convert OCR data
                conversion_result = self.parse_ocr_data(extraction)
                
                # Update provider stats
                provider = conversion_result.provider
                results['summary']['providers'][provider] = results['summary']['providers'].get(provider, 0) + 1
                
                if conversion_result.success:
                    results['summary']['successful'] += 1
                    results['summary']['total_tables'] += len(conversion_result.tables)
                    results['summary']['total_notes'] += len(conversion_result.notes)
                    
                    # Save files if output directory specified
                    if output_dir:
                        saved_files = self._save_conversion_files(conversion_result, output_path)
                        conversion_result.metadata['saved_files'] = saved_files
                    
                    self.logger.info(f"✓ {conversion_result.extraction_name}: "
                                   f"{len(conversion_result.tables)} table(s), "
                                   f"{len(conversion_result.notes)} note(s), "
                                   f"confidence: {conversion_result.confidence}%")
                else:
                    results['summary']['failed'] += 1
                    self.logger.warning(f"✗ {conversion_result.extraction_name}: {conversion_result.error}")
                
                results['conversions'].append(conversion_result)
        
        return results
    
    def _save_conversion_files(self, result: OCRExtractionResult, output_dir: Path) -> Dict:
        """Save converted tables and metadata to files"""
        
        saved_files = {}
        
        # Create equipment subdirectory
        eq_dir = output_dir / result.equipment_type
        eq_dir.mkdir(exist_ok=True)
        
        # Clean filename
        clean_name = "".join(c for c in result.extraction_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_name = clean_name.replace(' ', '_')
        
        coords = result.metadata.get('coordinates', {})
        page = coords.get('page', 'unknown')
        base_filename = f"{clean_name}_page{page}_{result.provider.lower().replace(' ', '_')}"
        
        # Save each table
        for i, df in enumerate(result.tables):
            table_suffix = f"_table{i+1}" if len(result.tables) > 1 else ""
            
            # CSV format
            csv_file = eq_dir / f"{base_filename}{table_suffix}.csv"
            df.to_csv(csv_file, index=False)
            saved_files[f'csv_table_{i+1}'] = str(csv_file)
            
            # Excel format
            excel_file = eq_dir / f"{base_filename}{table_suffix}.xlsx"
            df.to_excel(excel_file, index=False)
            saved_files[f'excel_table_{i+1}'] = str(excel_file)
            
            # Enhanced JSON with all metadata
            json_file = eq_dir / f"{base_filename}{table_suffix}_data.json"
            table_json = {
                'extraction_info': {
                    'name': result.extraction_name,
                    'equipment_type': result.equipment_type,
                    'page': page,
                    'provider': result.provider,
                    'confidence': result.confidence,
                    'extraction_type': result.metadata.get('extraction_type', 'unknown')
                },
                'table_data': {
                    'rows': len(df),
                    'columns': len(df.columns),
                    'headers': list(df.columns),
                    'data': df.values.tolist()
                },
                'notes': result.notes,
                'raw_ocr_text': result.raw_text,
                'coordinates': coords
            }
            
            with open(json_file, 'w') as f:
                json.dump(table_json, f, indent=2)
            saved_files[f'json_table_{i+1}'] = str(json_file)
        
        # Save notes as separate text file if available
        if result.notes:
            notes_file = eq_dir / f"{base_filename}_notes.txt"
            with open(notes_file, 'w') as f:
                f.write(f"Extraction: {result.extraction_name}\n")
                f.write(f"Equipment Type: {result.equipment_type}\n")
                f.write(f"OCR Provider: {result.provider}\n")
                f.write(f"Confidence: {result.confidence}%\n")
                f.write(f"Page: {page}\n")
                f.write(f"{'='*50}\n\n")
                f.write("INSTALLATION NOTES:\n\n")
                for i, note in enumerate(result.notes, 1):
                    f.write(f"{note}\n\n")
            saved_files['notes_file'] = str(notes_file)
        
        # Save raw OCR text
        raw_text_file = eq_dir / f"{base_filename}_raw_ocr.txt"
        with open(raw_text_file, 'w') as f:
            f.write(f"Extraction: {result.extraction_name}\n")
            f.write(f"OCR Provider: {result.provider}\n")
            f.write(f"Confidence: {result.confidence}%\n")
            f.write(f"{'='*50}\n\n")
            f.write(result.raw_text)
        saved_files['raw_text_file'] = str(raw_text_file)
        
        return saved_files
    
    def print_conversion_report(self, results: Dict):
        """Print comprehensive conversion report"""
        
        print(f"\n{'='*60}")
        print(f"EXISTING OCR DATA CONVERSION REPORT")
        print(f"{'='*60}")
        
        # Project info
        info = results['project_info']
        print(f"Project: {info['project']}")
        print(f"Export Date: {info['export_date']}")
        print(f"Total Extractions: {info['total_extractions']}")
        
        # Summary
        summary = results['summary']
        success_rate = (summary['successful'] / summary['total_processed'] * 100) if summary['total_processed'] > 0 else 0
        
        print(f"\n{'='*40}")
        print(f"CONVERSION SUMMARY")
        print(f"{'='*40}")
        print(f"Total processed: {summary['total_processed']}")
        print(f"Successful: {summary['successful']} ({success_rate:.1f}%)")
        print(f"Failed: {summary['failed']}")
        print(f"Total tables extracted: {summary['total_tables']}")
        print(f"Total notes extracted: {summary['total_notes']}")
        
        # Provider distribution
        if summary['providers']:
            print(f"\nOCR Providers:")
            for provider, count in summary['providers'].items():
                print(f"  {provider}: {count}")
        
        # Equipment breakdown
        equipment_stats = {}
        for conversion in results['conversions']:
            eq_type = conversion.equipment_type
            if eq_type not in equipment_stats:
                equipment_stats[eq_type] = {'total': 0, 'successful': 0, 'tables': 0, 'notes': 0}
            
            equipment_stats[eq_type]['total'] += 1
            if conversion.success:
                equipment_stats[eq_type]['successful'] += 1
                equipment_stats[eq_type]['tables'] += len(conversion.tables)
                equipment_stats[eq_type]['notes'] += len(conversion.notes)
        
        print(f"\n{'='*40}")
        print(f"EQUIPMENT TYPE BREAKDOWN")
        print(f"{'='*40}")
        for eq_type, stats in equipment_stats.items():
            print(f"{eq_type}:")
            print(f"  Total: {stats['total']}")
            print(f"  Successful: {stats['successful']}/{stats['total']}")
            print(f"  Tables: {stats['tables']}")
            print(f"  Notes: {stats['notes']}")
        
        # Individual results
        print(f"\n{'='*40}")
        print(f"INDIVIDUAL CONVERSION RESULTS")
        print(f"{'='*40}")
        
        for conversion in results['conversions']:
            coords = conversion.metadata.get('coordinates', {})
            print(f"\n{conversion.extraction_name} ({conversion.equipment_type}):")
            print(f"  Page: {coords.get('page', 'unknown')}")
            print(f"  OCR Provider: {conversion.provider}")
            print(f"  Confidence: {conversion.confidence}%")
            
            if conversion.success:
                print(f"  ✓ Success: {len(conversion.tables)} table(s), {len(conversion.notes)} note(s)")
                
                for i, df in enumerate(conversion.tables):
                    print(f"    Table {i+1}: {df.shape[0]} rows x {df.shape[1]} columns")
                    print(f"    Headers: {list(df.columns)}")
                
                if conversion.notes:
                    print(f"    Notes preview: {conversion.notes[0][:60]}...")
            else:
                print(f"  ✗ Failed: {conversion.error}")


def main():
    """Convert existing OCR data from JSON file"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert existing high-quality OCR data to structured tables')
    parser.add_argument('json_file', help='Path to PDF Extractor JSON file with OCR data')
    parser.add_argument('-o', '--output', help='Output directory for converted tables', default='converted_ocr_tables')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Initialize converter
    converter = ExistingOCRConverter(debug=args.debug)
    
    # Convert OCR data
    results = converter.convert_json_file(args.json_file, args.output)
    
    # Print report
    converter.print_conversion_report(results)
    
    # Show sample of first successful table
    successful_conversions = [c for c in results['conversions'] if c.success and c.tables]
    if successful_conversions:
        first_success = successful_conversions[0]
        df = first_success.tables[0]
        
        print(f"\n{'='*40}")
        print(f"SAMPLE TABLE: {first_success.extraction_name}")
        print(f"{'='*40}")
        print(df.head())
        
        if first_success.notes:
            print(f"\nSample notes:")
            for note in first_success.notes[:3]:
                print(f"  {note}")


if __name__ == '__main__':
    main()