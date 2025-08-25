#!/usr/bin/env python3
"""
BlueBeam Space Handler Module
=============================

Detects and manages BlueBeam Space objects in PDF documents.
Adapted from SpaceExtractor for integration with PDF Schedule Extractor.
"""

import fitz  # PyMuPDF
import re
import json
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class BlueBeamSpace:
    """Represents a BlueBeam Space object extracted from a PDF."""
    xref: int
    title: str
    coordinates: List[List[float]]  # [[x1,y1], [x2,y2], ...] - original BlueBeam coords
    page_number: int
    color: List[float]  # [r, g, b] values 0.0-1.0
    opacity: float  # 0.0-1.0
    bounds: Dict[str, float]  # min_x, min_y, max_x, max_y
    area: float
    pymupdf_rect: Optional[Tuple[float, float, float, float]] = None  # Transformed coordinates
    transformation_method: str = "default"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class BlueBeamSpaceHandler:
    """Handles detection and manipulation of BlueBeam Spaces in PDFs."""
    
    def __init__(self, pdf_path: str):
        """
        Initialize the handler with a PDF file path.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.doc = None
        self.spaces = []
        
    def __enter__(self):
        """Context manager entry."""
        self.doc = fitz.open(self.pdf_path)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.doc:
            self.doc.close()
    
    def detect_all_spaces(self) -> List[BlueBeamSpace]:
        """
        Detect all BlueBeam Spaces in the PDF.
        
        Returns:
            List of BlueBeamSpace objects found in the PDF
        """
        if not self.doc:
            self.doc = fitz.open(self.pdf_path)
        
        spaces = []
        page_space_map = {}
        
        # First, map spaces to pages by finding BSISpaces arrays
        for page_num in range(self.doc.page_count):
            try:
                page = self.doc[page_num]
                page_obj = self.doc.xref_object(page.xref)
                
                if page_obj and '/BSISpaces' in page_obj:
                    # Extract BSISpaces reference
                    bsi_match = re.search(r'/BSISpaces\s+(\d+)\s+0\s+R', page_obj)
                    if bsi_match:
                        bsi_xref = int(bsi_match.group(1))
                        
                        # Get the actual BSISpaces array
                        bsi_obj = self.doc.xref_object(bsi_xref)
                        if bsi_obj:
                            space_refs = self._extract_space_references(bsi_obj)
                            for space_ref in space_refs:
                                page_space_map[space_ref] = page_num
            except Exception as e:
                print(f"Error processing page {page_num}: {e}")
                continue
        
        # Then find all Space objects
        for xref in range(1, self.doc.xref_length()):
            try:
                obj_str = self.doc.xref_object(xref)
                if obj_str and '/Type /Space' in obj_str:
                    space = self._parse_space_object(xref, obj_str, page_space_map)
                    if space:
                        spaces.append(space)
            except Exception as e:
                print(f"Error processing xref {xref}: {e}")
                continue
        
        # Apply coordinate transformations to all spaces
        for space in spaces:
            self._transform_space_coordinates(space)
        
        self.spaces = spaces
        return spaces
    
    def _extract_space_references(self, bsi_obj_str: str) -> List[int]:
        """
        Extract space reference numbers from BSISpaces array.
        
        Args:
            bsi_obj_str: String representation of BSISpaces array object
            
        Returns:
            List of xref numbers
        """
        refs = []
        pattern = r'(\d+)\s+0\s+R'
        matches = re.findall(pattern, bsi_obj_str)
        for match in matches:
            refs.append(int(match))
        return refs
    
    def _parse_space_object(self, xref: int, obj_str: str, page_map: Dict[int, int]) -> Optional[BlueBeamSpace]:
        """
        Parse a Space object string into a BlueBeamSpace.
        
        Args:
            xref: Cross-reference number of the object
            obj_str: String representation of the Space object
            page_map: Mapping of xref to page numbers
            
        Returns:
            BlueBeamSpace object or None if parsing fails
        """
        try:
            # Extract title
            title_match = re.search(r'/Title\s*\((.*?)\)', obj_str)
            title = title_match.group(1) if title_match else f"Space_{xref}"
            
            # Extract path coordinates
            path_start = obj_str.find('/Path')
            if path_start == -1:
                return None
            
            # Find the opening bracket for the path array
            bracket_start = obj_str.find('[', path_start)
            if bracket_start == -1:
                return None
            
            # Find matching closing bracket using bracket counting
            bracket_count = 0
            bracket_end = -1
            for i in range(bracket_start, len(obj_str)):
                if obj_str[i] == '[':
                    bracket_count += 1
                elif obj_str[i] == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        bracket_end = i
                        break
            
            if bracket_end == -1:
                return None
            
            # Extract and parse coordinates
            path_str = obj_str[bracket_start + 1:bracket_end]
            coordinates = self._extract_path_coordinates(path_str)
            
            if not coordinates:
                return None
            
            # Determine page number
            page_number = page_map.get(xref, 0)
            
            # Extract color (default to blue if not found)
            color_match = re.search(r'/C\s*\[([\d\.\s]+)\]', obj_str)
            color = [0.0, 0.0, 1.0]  # Default blue
            if color_match:
                color_vals = [float(x) for x in color_match.group(1).split()]
                if len(color_vals) >= 3:
                    color = color_vals[:3]
            
            # Extract opacity (default to 0.25)
            opacity_match = re.search(r'/CA\s*([\d\.]+)', obj_str)
            opacity = float(opacity_match.group(1)) if opacity_match else 0.25
            
            # Calculate bounds and area
            x_coords = [coord[0] for coord in coordinates]
            y_coords = [coord[1] for coord in coordinates]
            bounds = {
                'min_x': min(x_coords),
                'min_y': min(y_coords),
                'max_x': max(x_coords),
                'max_y': max(y_coords)
            }
            
            # Simple area calculation (bounding rectangle)
            area = (bounds['max_x'] - bounds['min_x']) * (bounds['max_y'] - bounds['min_y'])
            
            return BlueBeamSpace(
                xref=xref,
                title=title,
                coordinates=coordinates,
                page_number=page_number,
                color=color,
                opacity=opacity,
                bounds=bounds,
                area=area
            )
            
        except Exception as e:
            print(f"Error parsing space {xref}: {e}")
            return None
    
    def _extract_path_coordinates(self, path_str: str) -> List[List[float]]:
        """
        Extract coordinate pairs from path string.
        
        Args:
            path_str: String containing coordinate arrays
            
        Returns:
            List of [x, y] coordinate pairs
        """
        coordinates = []
        
        # Remove extra whitespace
        path_str = re.sub(r'\s+', ' ', path_str.strip())
        
        # Find coordinate arrays marked by brackets
        i = 0
        while i < len(path_str):
            if path_str[i] == '[':
                # Found start of coordinate array
                bracket_count = 1
                start = i + 1
                i += 1
                
                # Find matching closing bracket
                while i < len(path_str) and bracket_count > 0:
                    if path_str[i] == '[':
                        bracket_count += 1
                    elif path_str[i] == ']':
                        bracket_count -= 1
                    i += 1
                
                if bracket_count == 0:
                    # Extract coordinates from this array
                    coord_str = path_str[start:i-1]
                    try:
                        coords = [float(x) for x in coord_str.split()]
                        if len(coords) >= 2:
                            coordinates.append([coords[0], coords[1]])
                    except ValueError:
                        continue
            else:
                i += 1
        
        return coordinates
    
    def _transform_space_coordinates(self, space: BlueBeamSpace) -> None:
        """
        Transform BlueBeam Space coordinates to PyMuPDF rectangle format.
        Based on SpaceExtractor coordinate_mapper.py logic.
        """
        if not self.doc or space.page_number >= self.doc.page_count:
            return
        
        x_coords = [coord[0] for coord in space.coordinates]
        y_coords = [coord[1] for coord in space.coordinates]
        
        x0 = min(x_coords)
        y0 = min(y_coords)
        x1 = max(x_coords)
        y1 = max(y_coords)
        
        page = self.doc[space.page_number]
        
        if page.rotation == 0:
            # Non-rotated page: Apply Y-flip transformation
            mediabox_height = page.mediabox.height
            flipped_y0 = mediabox_height - y1
            flipped_y1 = mediabox_height - y0
            space.pymupdf_rect = (x0, flipped_y0, x1, flipped_y1)
            space.transformation_method = "y_flip_transformation"
            
        elif page.rotation == 90:
            # 90° rotated page: Pass through coordinates as-is
            # The frontend will handle the rotation transformation (x,y) -> (y,x)
            space.pymupdf_rect = (x0, y0, x1, y1)
            space.transformation_method = "passthrough_90_rotation"
            
        else:
            # Other rotations: Use coordinates as-is (rotation normalization handles it)
            space.pymupdf_rect = (x0, y0, x1, y1)
            space.transformation_method = "rotation_normalization"
    
    def get_spaces_for_page(self, page_number: int) -> List[BlueBeamSpace]:
        """
        Get all spaces for a specific page.
        
        Args:
            page_number: Zero-based page number
            
        Returns:
            List of spaces on the specified page
        """
        return [space for space in self.spaces if space.page_number == page_number]
    
    def get_page_info(self, page_number: int) -> Dict:
        """
        Get information about a specific page.
        
        Args:
            page_number: Zero-based page number
            
        Returns:
            Dictionary with page information
        """
        if not self.doc or page_number >= self.doc.page_count:
            return {}
        
        page = self.doc[page_number]
        rect = page.rect
        
        return {
            'page_number': page_number,
            'width': rect.width,
            'height': rect.height,
            'rotation': page.rotation,
            'mediabox': {
                'x0': page.mediabox.x0,
                'y0': page.mediabox.y0,
                'x1': page.mediabox.x1,
                'y1': page.mediabox.y1
            }
        }
    
    def export_spaces_json(self, output_path: Optional[str] = None) -> str:
        """
        Export detected spaces to JSON format.
        
        Args:
            output_path: Optional output file path
            
        Returns:
            JSON string of spaces data
        """
        spaces_data = {
            'pdf_file': str(Path(self.pdf_path).name),
            'page_count': self.doc.page_count if self.doc else 0,
            'total_spaces': len(self.spaces),
            'spaces': [space.to_dict() for space in self.spaces],
            'pages': []
        }
        
        # Add page information
        if self.doc:
            for page_num in range(self.doc.page_count):
                page_info = self.get_page_info(page_num)
                page_spaces = self.get_spaces_for_page(page_num)
                page_info['space_count'] = len(page_spaces)
                page_info['space_xrefs'] = [s.xref for s in page_spaces]
                spaces_data['pages'].append(page_info)
        
        json_str = json.dumps(spaces_data, indent=2)
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(json_str)
        
        return json_str


def main():
    """Command-line interface for testing."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python bluebeam_space_handler.py <pdf_path>")
        return
    
    pdf_path = sys.argv[1]
    
    print(f"Detecting BlueBeam Spaces in: {pdf_path}")
    print("-" * 60)
    
    with BlueBeamSpaceHandler(pdf_path) as handler:
        spaces = handler.detect_all_spaces()
        
        if spaces:
            print(f"Found {len(spaces)} BlueBeam Spaces:")
            print("-" * 60)
            
            for space in spaces:
                print(f"Title: {space.title}")
                print(f"  Page: {space.page_number + 1}")
                print(f"  Color: RGB({space.color[0]:.2f}, {space.color[1]:.2f}, {space.color[2]:.2f})")
                print(f"  Opacity: {space.opacity:.2f}")
                print(f"  Area: {space.area:.1f} sq points")
                print(f"  Bounds: ({space.bounds['min_x']:.1f}, {space.bounds['min_y']:.1f}) to "
                      f"({space.bounds['max_x']:.1f}, {space.bounds['max_y']:.1f})")
                print(f"  Coordinates: {len(space.coordinates)} points")
                print("-" * 60)
            
            # Export to JSON
            json_output = pdf_path.replace('.pdf', '_spaces.json')
            handler.export_spaces_json(json_output)
            print(f"Exported spaces to: {json_output}")
        else:
            print("No BlueBeam Spaces found in this PDF")


if __name__ == "__main__":
    main()