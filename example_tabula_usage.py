#!/usr/bin/env python3
"""
Example Usage: PDF Extractor + tabula-py Integration

This demonstrates how to use the coordinate converter to extract tables
with tabula-py using coordinates from the PDF Extractor tool.
"""

from tabula_coordinate_converter import TabulaCoordinateConverter
import json

def simple_extraction_example():
    """Basic example: Extract one table using coordinates"""
    
    # Sample coordinates from PDF Extractor JSON
    coords = {
        "x": 1844.67,
        "y": 232.67, 
        "width": 392.67,
        "height": 294.67,
        "page": 2
    }
    
    # Initialize converter
    converter = TabulaCoordinateConverter('your_pdf_file.pdf')
    
    # Convert coordinates to tabula-py format
    area = converter.convert_coordinates(coords)
    print(f"Converted area: {area}")
    # Output: [top, left, bottom, right] for tabula-py
    
    # Extract table
    tables = converter.extract_table_from_coordinates(coords)
    
    if tables:
        df = tables[0]  # First table
        print(f"Extracted table shape: {df.shape}")
        print(df.head())
    else:
        print("No tables found")

def batch_processing_example():
    """Process entire PDF Extractor JSON file"""
    
    # Initialize converter
    converter = TabulaCoordinateConverter('sample.pdf')
    
    # Process all extractions from JSON
    results = converter.process_extraction_json(
        'project_data.json',
        output_dir='tabula_extractions'  # Save CSV files here
    )
    
    # Review results
    print(f"Processed {results['total_processed']} extractions")
    print(f"Successful: {len(results['successful_extractions'])}")
    print(f"Failed: {len(results['failed_extractions'])}")
    
    # Access individual results
    for extraction in results['successful_extractions']:
        print(f"✓ {extraction['name']}: {extraction['table_count']} tables")
        for table in extraction['tables']:
            print(f"  - Table shape: {table.shape}")

def advanced_extraction_example():
    """Advanced usage with custom tabula-py settings"""
    
    converter = TabulaCoordinateConverter('construction_schedule.pdf')
    
    coords = {
        "x": 100,
        "y": 200,
        "width": 500,
        "height": 300,
        "page": 1
    }
    
    # Custom tabula-py parameters for difficult tables
    custom_settings = {
        'lattice': False,           # Use stream method instead
        'stream': True,
        'guess': False,             # Don't auto-detect areas
        'pandas_options': {
            'header': [0, 1]        # Multi-level headers
        },
        'columns': [150, 300, 450], # Specify column boundaries
        'encoding': 'utf-8'
    }
    
    tables = converter.extract_table_from_coordinates(coords, **custom_settings)
    
    if tables:
        df = tables[0]
        # Clean up the extracted data
        df = df.dropna(how='all')  # Remove empty rows
        df.columns = df.columns.str.strip()  # Clean column names
        print(df)

def coordinate_debugging_example():
    """Debug coordinate conversion issues"""
    
    converter = TabulaCoordinateConverter('problem.pdf')
    
    # Your PDF Extractor coordinates
    coords = {
        "x": 1844.67,
        "y": 232.67,
        "width": 392.67, 
        "height": 294.67,
        "page": 2
    }
    
    # Get page dimensions
    page_width, page_height = converter.page_dimensions[coords['page']]
    print(f"Page {coords['page']} dimensions: {page_width} x {page_height}")
    
    # Show coordinate conversion step by step
    x, y, width, height = coords['x'], coords['y'], coords['width'], coords['height']
    
    print(f"Original coordinates (top-left origin):")
    print(f"  x: {x}, y: {y}, width: {width}, height: {height}")
    
    # Manual conversion
    top = page_height - y - height
    left = x  
    bottom = page_height - y
    right = x + width
    
    print(f"Converted coordinates (bottom-left origin):")
    print(f"  top: {top}, left: {left}, bottom: {bottom}, right: {right}")
    
    # Verify conversion
    area = converter.convert_coordinates(coords)
    print(f"tabula-py area: {area}")
    
    # Check if coordinates are within page bounds
    if top < 0 or left < 0 or bottom > page_height or right > page_width:
        print("⚠️  WARNING: Coordinates extend outside page bounds!")
    else:
        print("✓ Coordinates are within page bounds")

def troubleshooting_example():
    """Common issues and solutions"""
    
    converter = TabulaCoordinateConverter('document.pdf')
    
    coords = {"x": 100, "y": 200, "width": 400, "height": 300, "page": 1}
    
    # Try multiple extraction strategies
    strategies = [
        {'lattice': True, 'stream': False},   # Method 1: Lattice (bordered tables)
        {'lattice': False, 'stream': True},   # Method 2: Stream (no borders)
        {'lattice': True, 'multiple_tables': True},  # Method 3: Multiple tables
        {'guess': True}  # Method 4: Auto-detect (ignores area)
    ]
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\nTrying strategy {i}: {strategy}")
        try:
            tables = converter.extract_table_from_coordinates(coords, **strategy)
            if tables:
                print(f"✓ Success! Found {len(tables)} table(s)")
                print(f"  First table shape: {tables[0].shape}")
                break
            else:
                print("✗ No tables found")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # If all strategies fail, the coordinates might be wrong
    # or the area might not contain a recognizable table

if __name__ == '__main__':
    print("=== PDF Extractor + tabula-py Examples ===\n")
    
    # Uncomment the example you want to run:
    
    # simple_extraction_example()
    # batch_processing_example() 
    # advanced_extraction_example()
    coordinate_debugging_example()
    # troubleshooting_example()