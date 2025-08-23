#!/usr/bin/env python3
"""
Hybrid Table Extractor: Text + OCR for PDF Extractor Coordinates

Handles both text-based tables and image-based tables using:
- Text extraction: tabula-py, camelot-py, pdfplumber
- OCR extraction: pytesseract, easyocr, Google Gemini API
- Intelligent detection of table type (text vs image)

Installation:
pip install tabula-py camelot-py[cv] pdfplumber pytesseract easyocr pdf2image pillow

System dependencies:
- Tesseract: sudo apt-get install tesseract-ocr
- Poppler: sudo apt-get install poppler-utils
"""

import json
import pandas as pd
import numpy as np
import os
import io
import base64
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum
import re

# Import existing libraries
try:
    import tabula
    TABULA_AVAILABLE = True
except ImportError:
    TABULA_AVAILABLE = False

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

# OCR libraries
try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    print("Warning: pytesseract not available. Install with: pip install pytesseract pillow")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    print("Warning: easyocr not available. Install with: pip install easyocr")

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    print("Warning: pdf2image not available. Install with: pip install pdf2image")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: opencv-python not available. Install with: pip install opencv-python")

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

# Google Gemini API (reuse existing implementation)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: Google Gemini not available. Install with: pip install google-generativeai")


class TableType(Enum):
    """Table content type"""
    TEXT = "text"           # Selectable text
    IMAGE = "image"         # Scanned/image table
    MIXED = "mixed"         # Combination
    UNKNOWN = "unknown"


class ExtractionStrategy(Enum):
    """Extraction approach"""
    TEXT_EXTRACTION = "text"
    OCR_TESSERACT = "ocr_tesseract"
    OCR_EASYOCR = "ocr_easyocr"
    OCR_GEMINI = "ocr_gemini"
    HYBRID = "hybrid"


@dataclass
class HybridExtractionResult:
    """Enhanced extraction result with table type info"""
    method: str
    table_type: TableType
    success: bool
    tables: List[pd.DataFrame]
    confidence: float
    raw_text: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None


class HybridTableExtractor:
    """Intelligent extractor for both text and image-based tables"""
    
    def __init__(self, pdf_path: str, gemini_api_key: Optional[str] = None, debug: bool = False):
        """
        Initialize hybrid extractor
        
        Args:
            pdf_path: Path to PDF file
            gemini_api_key: Google Gemini API key for OCR
            debug: Enable debug logging
        """
        self.pdf_path = Path(pdf_path)
        self.gemini_api_key = gemini_api_key
        self.debug = debug
        self.page_dimensions = self._get_page_dimensions()
        
        # Setup logging
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize OCR components
        self._setup_ocr()
        
        # Validate dependencies
        self._validate_dependencies()
    
    def _setup_ocr(self):
        """Setup OCR engines"""
        self.easyocr_reader = None
        self.gemini_model = None
        
        # Setup EasyOCR
        if EASYOCR_AVAILABLE:
            try:
                self.easyocr_reader = easyocr.Reader(['en'])
                self.logger.info("EasyOCR initialized")
            except Exception as e:
                self.logger.warning(f"EasyOCR initialization failed: {e}")
        
        # Setup Gemini
        if GEMINI_AVAILABLE and self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
                self.logger.info("Google Gemini initialized")
            except Exception as e:
                self.logger.warning(f"Gemini initialization failed: {e}")
    
    def _validate_dependencies(self):
        """Check available extraction methods"""
        text_methods = []
        ocr_methods = []
        
        if TABULA_AVAILABLE:
            text_methods.append("tabula-py")
        if CAMELOT_AVAILABLE:
            text_methods.append("camelot-py")
        if PDFPLUMBER_AVAILABLE:
            text_methods.append("pdfplumber")
        
        if PYTESSERACT_AVAILABLE:
            ocr_methods.append("pytesseract")
        if EASYOCR_AVAILABLE:
            ocr_methods.append("easyocr")
        if self.gemini_model:
            ocr_methods.append("gemini")
        
        self.logger.info(f"Text extraction: {', '.join(text_methods) if text_methods else 'None'}")
        self.logger.info(f"OCR extraction: {', '.join(ocr_methods) if ocr_methods else 'None'}")
        
        if not text_methods and not ocr_methods:
            raise ImportError("No extraction methods available")
    
    def _get_page_dimensions(self) -> Dict[int, Tuple[float, float]]:
        """Get page dimensions for coordinate conversion"""
        dimensions = {}
        
        if not PYPDF2_AVAILABLE:
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
    
    def detect_table_type(self, coords: Dict) -> TableType:
        """Detect if table area contains selectable text or is an image"""
        
        if not PDFPLUMBER_AVAILABLE:
            return TableType.UNKNOWN
        
        try:
            _, formats = self._convert_coordinates(coords)
            page_num = coords['page']
            bbox = formats['pdfplumber_bbox']
            
            with pdfplumber.open(self.pdf_path) as pdf:
                if page_num > len(pdf.pages):
                    return TableType.UNKNOWN
                
                page = pdf.pages[page_num - 1]
                cropped = page.crop(bbox)
                
                # Check for selectable text
                text = cropped.extract_text()
                
                # Check for images
                images = cropped.images
                
                # Analyze content
                has_substantial_text = text and len(text.strip()) > 20
                has_images = len(images) > 0
                
                # Check if text looks like table data
                if has_substantial_text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    # Look for table patterns
                    table_indicators = 0
                    for line in lines:
                        # Check for multiple words/numbers separated by spaces
                        words = line.split()
                        if len(words) >= 3:
                            table_indicators += 1
                        
                        # Check for common table patterns
                        if re.search(r'\d+\s+[A-Za-z]', line) or re.search(r'[A-Za-z]+\s+\d+', line):
                            table_indicators += 1
                    
                    text_table_likelihood = table_indicators / max(len(lines), 1)
                    
                    if has_images and text_table_likelihood < 0.3:
                        return TableType.MIXED
                    elif text_table_likelihood >= 0.3:
                        return TableType.TEXT
                
                if has_images:
                    return TableType.IMAGE
                
                return TableType.UNKNOWN
                
        except Exception as e:
            self.logger.warning(f"Table type detection failed: {e}")
            return TableType.UNKNOWN
    
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
            'original': coords,
            'crop_box': (int(left), int(top), int(right), int(bottom))  # For PIL cropping
        }
        
        return formats['tabula_area'], formats
    
    def extract_with_text_methods(self, coords: Dict) -> HybridExtractionResult:
        """Extract using text-based methods (from previous implementation)"""
        # This reuses the intelligent text extraction logic
        from intelligent_table_extractor import IntelligentTableExtractor
        
        try:
            text_extractor = IntelligentTableExtractor(str(self.pdf_path), self.debug)
            result = text_extractor.extract_table_intelligent(coords)
            
            return HybridExtractionResult(
                method=result.method,
                table_type=TableType.TEXT,
                success=result.success,
                tables=result.tables,
                confidence=result.confidence,
                error=result.error,
                metadata=result.metadata
            )
        except Exception as e:
            return HybridExtractionResult(
                method="text_extraction",
                table_type=TableType.TEXT,
                success=False,
                tables=[],
                confidence=0.0,
                error=str(e)
            )
    
    def extract_page_as_image(self, page_num: int, coords: Dict) -> Optional[Image.Image]:
        """Extract page region as image for OCR"""
        if not PDF2IMAGE_AVAILABLE:
            self.logger.error("pdf2image not available")
            return None
        
        try:
            # Convert PDF page to image
            images = convert_from_path(
                self.pdf_path,
                first_page=page_num,
                last_page=page_num,
                dpi=300  # High DPI for better OCR
            )
            
            if not images:
                return None
            
            page_image = images[0]
            
            # Calculate crop coordinates
            # pdf2image uses 72 DPI as base, we're using 300 DPI
            scale_factor = 300 / 72
            
            _, formats = self._convert_coordinates(coords)
            left, top, right, bottom = formats['crop_box']
            
            # Scale coordinates to image DPI
            crop_left = int(left * scale_factor)
            crop_top = int(top * scale_factor)
            crop_right = int(right * scale_factor)
            crop_bottom = int(bottom * scale_factor)
            
            # Crop the image
            cropped = page_image.crop((crop_left, crop_top, crop_right, crop_bottom))
            
            return cropped
            
        except Exception as e:
            self.logger.error(f"Image extraction failed: {e}")
            return None
    
    def preprocess_image_for_ocr(self, image: Image.Image) -> Image.Image:
        """Enhance image quality for better OCR results"""
        if not CV2_AVAILABLE:
            return image
        
        try:
            # Convert PIL to OpenCV
            img_array = np.array(image)
            
            # Convert to grayscale
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Apply image enhancements
            # 1. Noise reduction
            denoised = cv2.medianBlur(gray, 3)
            
            # 2. Contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(denoised)
            
            # 3. Threshold for better text recognition
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Convert back to PIL
            processed_image = Image.fromarray(binary)
            
            return processed_image
            
        except Exception as e:
            self.logger.warning(f"Image preprocessing failed: {e}")
            return image
    
    def extract_with_tesseract(self, coords: Dict) -> HybridExtractionResult:
        """Extract table using Tesseract OCR"""
        if not PYTESSERACT_AVAILABLE:
            return HybridExtractionResult(
                "tesseract", TableType.IMAGE, False, [], 0.0,
                error="pytesseract not available"
            )
        
        try:
            page_num = coords['page']
            image = self.extract_page_as_image(page_num, coords)
            
            if not image:
                return HybridExtractionResult(
                    "tesseract", TableType.IMAGE, False, [], 0.0,
                    error="Could not extract image"
                )
            
            # Preprocess image
            processed_image = self.preprocess_image_for_ocr(image)
            
            # OCR with table-optimized settings
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,()-/ '
            
            # Extract text
            raw_text = pytesseract.image_to_string(processed_image, config=custom_config)
            
            # Parse text into table structure
            df = self._parse_ocr_text_to_table(raw_text)
            
            if df is not None and not df.empty:
                confidence = self._calculate_ocr_confidence(df, raw_text)
                return HybridExtractionResult(
                    "tesseract", TableType.IMAGE, True, [df], confidence,
                    raw_text=raw_text
                )
            else:
                return HybridExtractionResult(
                    "tesseract", TableType.IMAGE, False, [], 0.0,
                    raw_text=raw_text, error="Could not parse table structure"
                )
                
        except Exception as e:
            return HybridExtractionResult(
                "tesseract", TableType.IMAGE, False, [], 0.0,
                error=str(e)
            )
    
    def extract_with_easyocr(self, coords: Dict) -> HybridExtractionResult:
        """Extract table using EasyOCR"""
        if not EASYOCR_AVAILABLE or not self.easyocr_reader:
            return HybridExtractionResult(
                "easyocr", TableType.IMAGE, False, [], 0.0,
                error="easyocr not available"
            )
        
        try:
            page_num = coords['page']
            image = self.extract_page_as_image(page_num, coords)
            
            if not image:
                return HybridExtractionResult(
                    "easyocr", TableType.IMAGE, False, [], 0.0,
                    error="Could not extract image"
                )
            
            # Convert PIL to numpy array for EasyOCR
            img_array = np.array(image)
            
            # Extract text with bounding boxes
            results = self.easyocr_reader.readtext(img_array)
            
            # Reconstruct text in reading order
            raw_text = self._reconstruct_text_from_boxes(results)
            
            # Parse text into table structure
            df = self._parse_ocr_text_to_table(raw_text)
            
            if df is not None and not df.empty:
                # EasyOCR provides confidence scores
                avg_confidence = np.mean([result[2] for result in results]) * 100
                confidence = min(avg_confidence, self._calculate_ocr_confidence(df, raw_text))
                
                return HybridExtractionResult(
                    "easyocr", TableType.IMAGE, True, [df], confidence,
                    raw_text=raw_text,
                    metadata={'ocr_boxes': results}
                )
            else:
                return HybridExtractionResult(
                    "easyocr", TableType.IMAGE, False, [], 0.0,
                    raw_text=raw_text, error="Could not parse table structure"
                )
                
        except Exception as e:
            return HybridExtractionResult(
                "easyocr", TableType.IMAGE, False, [], 0.0,
                error=str(e)
            )
    
    def extract_with_gemini(self, coords: Dict) -> HybridExtractionResult:
        """Extract table using Google Gemini API OCR"""
        if not self.gemini_model:
            return HybridExtractionResult(
                "gemini", TableType.IMAGE, False, [], 0.0,
                error="Gemini not available"
            )
        
        try:
            page_num = coords['page']
            image = self.extract_page_as_image(page_num, coords)
            
            if not image:
                return HybridExtractionResult(
                    "gemini", TableType.IMAGE, False, [], 0.0,
                    error="Could not extract image"
                )
            
            # Convert image to base64 for Gemini
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            image_data = base64.b64encode(buffer.getvalue()).decode()
            
            # Gemini prompt optimized for construction schedules
            prompt = """
            Analyze this construction schedule table image and extract the data in a structured format.

            Please provide:
            1. A clean table structure with properly aligned columns
            2. Preserve all numerical values, units, and technical specifications
            3. Identify column headers accurately
            4. Handle any merged cells or complex layouts
            5. Extract any notes or footnotes

            Return the data in a clear, tabular text format that can be easily parsed.
            """
            
            # Call Gemini API
            response = self.gemini_model.generate_content([
                {"mime_type": "image/png", "data": image_data},
                prompt
            ])
            
            raw_text = response.text
            
            # Parse Gemini response into table structure
            df = self._parse_gemini_response_to_table(raw_text)
            
            if df is not None and not df.empty:
                confidence = self._calculate_ocr_confidence(df, raw_text)
                # Gemini typically has higher confidence for complex layouts
                confidence = min(95.0, confidence + 10)
                
                return HybridExtractionResult(
                    "gemini", TableType.IMAGE, True, [df], confidence,
                    raw_text=raw_text,
                    metadata={'gemini_response': raw_text}
                )
            else:
                return HybridExtractionResult(
                    "gemini", TableType.IMAGE, False, [], 0.0,
                    raw_text=raw_text, error="Could not parse Gemini response"
                )
                
        except Exception as e:
            return HybridExtractionResult(
                "gemini", TableType.IMAGE, False, [], 0.0,
                error=str(e)
            )
    
    def _reconstruct_text_from_boxes(self, ocr_results: List) -> str:
        """Reconstruct text from OCR bounding boxes in reading order"""
        if not ocr_results:
            return ""
        
        # Sort by Y coordinate (top to bottom), then X coordinate (left to right)
        sorted_results = sorted(ocr_results, key=lambda x: (x[0][0][1], x[0][0][0]))
        
        # Group into lines based on Y coordinate similarity
        lines = []
        current_line = []
        current_y = None
        
        for result in sorted_results:
            text = result[1]
            bbox = result[0]
            y_center = (bbox[0][1] + bbox[2][1]) / 2
            
            if current_y is None or abs(y_center - current_y) < 20:  # Same line threshold
                current_line.append(text)
                current_y = y_center
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [text]
                current_y = y_center
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    def _parse_ocr_text_to_table(self, raw_text: str) -> Optional[pd.DataFrame]:
        """Parse OCR text into DataFrame table structure"""
        if not raw_text or not raw_text.strip():
            return None
        
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        
        if len(lines) < 2:  # Need at least header + 1 data row
            return None
        
        # Try to identify table structure
        table_data = []
        
        for line in lines:
            # Split on multiple spaces or tabs
            row = re.split(r'\s{2,}|\t', line)
            # Clean empty elements
            row = [cell.strip() for cell in row if cell.strip()]
            
            if len(row) >= 2:  # Valid table row
                table_data.append(row)
        
        if len(table_data) < 2:
            return None
        
        # Create DataFrame
        try:
            # Use first row as headers
            headers = table_data[0]
            data_rows = table_data[1:]
            
            # Ensure all rows have same number of columns
            max_cols = max(len(row) for row in data_rows) if data_rows else len(headers)
            
            # Pad rows to same length
            normalized_data = []
            for row in data_rows:
                padded_row = row + [''] * (max_cols - len(row))
                normalized_data.append(padded_row[:max_cols])
            
            # Pad headers if needed
            padded_headers = headers + [f'Column_{i}' for i in range(len(headers), max_cols)]
            padded_headers = padded_headers[:max_cols]
            
            df = pd.DataFrame(normalized_data, columns=padded_headers)
            return df
            
        except Exception as e:
            self.logger.warning(f"Table parsing failed: {e}")
            return None
    
    def _parse_gemini_response_to_table(self, gemini_text: str) -> Optional[pd.DataFrame]:
        """Parse Gemini API response into DataFrame"""
        # Gemini often returns markdown tables or structured text
        # Try to extract table data from the response
        
        lines = gemini_text.split('\n')
        table_lines = []
        
        # Look for table-like structures
        for line in lines:
            line = line.strip()
            
            # Skip markdown table separators
            if re.match(r'^[\|\-\s]+$', line):
                continue
            
            # Look for pipe-separated tables (markdown)
            if '|' in line:
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if len(cells) >= 2:
                    table_lines.append(cells)
            
            # Look for tab/space separated data
            elif re.search(r'\w+\s+\w+', line) and not line.startswith('#'):
                cells = re.split(r'\s{2,}|\t', line)
                cells = [cell.strip() for cell in cells if cell.strip()]
                if len(cells) >= 2:
                    table_lines.append(cells)
        
        if len(table_lines) < 2:
            # Fallback to general text parsing
            return self._parse_ocr_text_to_table(gemini_text)
        
        try:
            headers = table_lines[0]
            data_rows = table_lines[1:]
            
            # Normalize row lengths
            max_cols = max(len(row) for row in data_rows + [headers])
            
            normalized_data = []
            for row in data_rows:
                padded_row = row + [''] * (max_cols - len(row))
                normalized_data.append(padded_row[:max_cols])
            
            padded_headers = headers + [f'Column_{i}' for i in range(len(headers), max_cols)]
            padded_headers = padded_headers[:max_cols]
            
            df = pd.DataFrame(normalized_data, columns=padded_headers)
            return df
            
        except Exception as e:
            self.logger.warning(f"Gemini response parsing failed: {e}")
            return None
    
    def _calculate_ocr_confidence(self, df: pd.DataFrame, raw_text: str) -> float:
        """Calculate confidence score for OCR-extracted table"""
        if df.empty:
            return 0.0
        
        score = 0.0
        
        # Factor 1: Table structure (0-30 points)
        if df.shape[0] >= 2 and df.shape[1] >= 2:
            score += 30
        elif df.shape[0] >= 1 and df.shape[1] >= 2:
            score += 20
        
        # Factor 2: Data completeness (0-25 points)
        total_cells = df.shape[0] * df.shape[1]
        non_empty_cells = (df != '').sum().sum()
        completeness = non_empty_cells / total_cells if total_cells > 0 else 0
        score += completeness * 25
        
        # Factor 3: Text quality indicators (0-25 points)
        text_quality = 0
        if raw_text:
            # Check for common OCR artifacts
            artifact_ratio = len(re.findall(r'[^\w\s\.,\-\(\)\/]', raw_text)) / max(len(raw_text), 1)
            text_quality = max(0, 1 - artifact_ratio * 5) * 25
        score += text_quality
        
        # Factor 4: Numeric data presence (0-20 points)
        numeric_score = 0
        for col in df.columns:
            numeric_vals = pd.to_numeric(df[col], errors='coerce').notna().sum()
            if numeric_vals > 0:
                numeric_score += min(10, numeric_vals * 2)
        score += min(20, numeric_score)
        
        return min(100.0, score)
    
    def extract_table_hybrid(self, coords: Dict) -> HybridExtractionResult:
        """Intelligent hybrid extraction using table type detection"""
        
        self.logger.info(f"Starting hybrid extraction for page {coords['page']}")
        
        # Step 1: Detect table type
        table_type = self.detect_table_type(coords)
        self.logger.info(f"Detected table type: {table_type.value}")
        
        # Step 2: Choose extraction strategy based on type
        if table_type == TableType.TEXT:
            # Try text-based extraction first
            result = self.extract_with_text_methods(coords)
            
            if result.success and result.confidence >= 60:
                return result
            
            # Fallback to OCR if text extraction fails
            self.logger.info("Text extraction failed, trying OCR fallback")
            
        # Step 3: OCR-based extraction
        ocr_results = []
        
        # Try Gemini first (usually best for complex layouts)
        if self.gemini_model:
            gemini_result = self.extract_with_gemini(coords)
            ocr_results.append(gemini_result)
            if gemini_result.success and gemini_result.confidence >= 70:
                return gemini_result
        
        # Try EasyOCR
        if self.easyocr_reader:
            easyocr_result = self.extract_with_easyocr(coords)
            ocr_results.append(easyocr_result)
            if easyocr_result.success and easyocr_result.confidence >= 65:
                return easyocr_result
        
        # Try Tesseract
        if PYTESSERACT_AVAILABLE:
            tesseract_result = self.extract_with_tesseract(coords)
            ocr_results.append(tesseract_result)
        
        # Return best OCR result
        successful_results = [r for r in ocr_results if r.success]
        if successful_results:
            best_result = max(successful_results, key=lambda x: x.confidence)
            return best_result
        
        # If everything fails, try text extraction as last resort
        if table_type != TableType.TEXT:
            text_result = self.extract_with_text_methods(coords)
            if text_result.success:
                return text_result
        
        # Return best attempt even if unsuccessful
        all_results = ocr_results + ([result] if 'result' in locals() else [])
        if all_results:
            return max(all_results, key=lambda x: x.confidence)
        
        return HybridExtractionResult(
            "hybrid", table_type, False, [], 0.0,
            error="All extraction methods failed"
        )
    
    def process_extraction_json(self, json_path: str, output_dir: Optional[str] = None) -> Dict:
        """Process PDF Extractor JSON with hybrid extraction"""
        
        self.logger.info(f"Processing JSON file with hybrid extraction: {json_path}")
        
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        results = {
            'successful_extractions': [],
            'failed_extractions': [],
            'total_processed': 0,
            'extraction_summary': {},
            'method_distribution': {}
        }
        
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Process each extraction
        for equipment_type, extractions in data.get('equipment', {}).items():
            self.logger.info(f"Processing {len(extractions)} extractions for {equipment_type}")
            
            for extraction in extractions:
                results['total_processed'] += 1
                
                extraction_name = extraction.get('extractionName', f"extraction_{extraction.get('id', 'unknown')}")
                coords = extraction['coordinates']
                
                try:
                    # Hybrid extraction
                    result = self.extract_table_hybrid(coords)
                    
                    # Track method usage
                    method = result.method
                    results['method_distribution'][method] = results['method_distribution'].get(method, 0) + 1
                    
                    if result.success and result.tables:
                        extraction_result = {
                            'extraction_id': extraction.get('id'),
                            'name': extraction_name,
                            'equipment_type': equipment_type,
                            'extraction_type': extraction.get('extractionType', 'unknown'),
                            'page': coords['page'],
                            'coordinates': coords,
                            'method_used': method,
                            'table_type': result.table_type.value,
                            'confidence': result.confidence,
                            'table_count': len(result.tables),
                            'tables': result.tables,
                            'raw_text': result.raw_text
                        }
                        
                        # Save files
                        if output_dir:
                            saved_files = self._save_extraction_files(extraction_result, output_path)
                            extraction_result['saved_files'] = saved_files
                        
                        results['successful_extractions'].append(extraction_result)
                        
                        self.logger.info(f"✓ {extraction_name}: {len(result.tables)} table(s) using {method} "
                                       f"(type: {result.table_type.value}, confidence: {result.confidence:.1f})")
                    else:
                        error_msg = result.error or "No tables extracted"
                        results['failed_extractions'].append({
                            'extraction_id': extraction.get('id'),
                            'name': extraction_name,
                            'equipment_type': equipment_type,
                            'method_attempted': method,
                            'table_type': result.table_type.value,
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
        
        self.logger.info(f"Hybrid extraction complete: {successful}/{total} successful "
                        f"({results['extraction_summary']['success_rate']:.1f}%)")
        
        return results
    
    def _save_extraction_files(self, extraction_result: Dict, output_dir: Path) -> Dict:
        """Save extracted tables with OCR metadata"""
        saved_files = {}
        
        equipment_type = extraction_result['equipment_type']
        name = extraction_result['name']
        page = extraction_result['page']
        method = extraction_result['method_used']
        table_type = extraction_result['table_type']
        
        # Create equipment subdirectory
        eq_dir = output_dir / equipment_type
        eq_dir.mkdir(exist_ok=True)
        
        # Clean filename
        clean_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_name = clean_name.replace(' ', '_')
        
        base_filename = f"{clean_name}_page{page}_{method}"
        
        # Save each table
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
            
            # Enhanced JSON with extraction metadata
            json_file = eq_dir / f"{base_filename}{table_suffix}_data.json"
            table_json = {
                'extraction_info': {
                    'name': name,
                    'equipment_type': equipment_type,
                    'page': page,
                    'method': method,
                    'table_type': table_type,
                    'confidence': extraction_result['confidence']
                },
                'table_data': {
                    'rows': len(df),
                    'columns': len(df.columns),
                    'headers': list(df.columns),
                    'data': df.values.tolist()
                },
                'raw_ocr_text': extraction_result.get('raw_text', '')
            }
            
            with open(json_file, 'w') as f:
                json.dump(table_json, f, indent=2)
            saved_files[f'json_table_{i+1}'] = str(json_file)
            
            # Save raw OCR text if available
            if extraction_result.get('raw_text'):
                txt_file = eq_dir / f"{base_filename}{table_suffix}_ocr.txt"
                with open(txt_file, 'w') as f:
                    f.write(f"Extraction Method: {method}\n")
                    f.write(f"Table Type: {table_type}\n")
                    f.write(f"Confidence: {extraction_result['confidence']:.1f}%\n")
                    f.write(f"{'='*50}\n\n")
                    f.write(extraction_result['raw_text'])
                saved_files[f'ocr_text_{i+1}'] = str(txt_file)
        
        return saved_files


def main():
    """Command line interface for hybrid extraction"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Hybrid Table Extractor: Text + OCR for PDF Extractor coordinates')
    parser.add_argument('pdf_file', help='Path to PDF file')
    parser.add_argument('json_file', help='Path to PDF Extractor JSON file')
    parser.add_argument('-o', '--output', help='Output directory for extracted tables', default='hybrid_extracted_tables')
    parser.add_argument('--gemini-key', help='Google Gemini API key for enhanced OCR')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Initialize hybrid extractor
    extractor = HybridTableExtractor(args.pdf_file, args.gemini_key, debug=args.debug)
    
    # Process JSON file
    results = extractor.process_extraction_json(args.json_file, args.output)
    
    # Print comprehensive summary
    summary = results['extraction_summary']
    methods = results['method_distribution']
    
    print(f"\n{'='*60}")
    print(f"HYBRID EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total processed: {summary['total_processed']}")
    print(f"Successful: {summary['successful']} ({summary['success_rate']:.1f}%)")
    print(f"Failed: {summary['failed']}")
    
    if methods:
        print(f"\nExtraction methods used:")
        for method, count in sorted(methods.items()):
            print(f"  {method}: {count}")
    
    # Show table type distribution
    if results['successful_extractions']:
        table_types = {}
        for extraction in results['successful_extractions']:
            table_type = extraction['table_type']
            table_types[table_type] = table_types.get(table_type, 0) + 1
        
        print(f"\nTable types detected:")
        for table_type, count in sorted(table_types.items()):
            print(f"  {table_type}: {count}")
        
        print(f"\nFiles saved to: {args.output}")
    
    if results['failed_extractions']:
        print(f"\nFailed extractions:")
        for failure in results['failed_extractions']:
            method = failure.get('method_attempted', 'unknown')
            table_type = failure.get('table_type', 'unknown')
            print(f"  - {failure['name']} ({method}, {table_type}): {failure['error']}")


if __name__ == '__main__':
    main()