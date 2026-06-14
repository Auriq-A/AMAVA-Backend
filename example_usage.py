"""
Example usage of the JSON Merger & Excel Converter
"""

from out.merge_json_to_excel import JSONMergerExcelConverter
import os


def example_1_merge_json_files_in_folder():
    """
    Example 1: Merge all JSON files in a folder and create Excel
    """
    print("\n" + "="*60)
    print("Example 1: Merge JSON files from a folder")
    print("="*60)
    
    # Specify the folder containing JSON files
    json_folder = "JSON FILES"  # or any folder with JSON files
    
    # Create converter
    converter = JSONMergerExcelConverter(
        json_folder=json_folder,
        output_file="merged_output_nested.xlsx"
    )
    
    # Process with nested structure (creates one sheet per product)
    converter.process(use_flat=False)


def example_2_merge_with_flat_structure():
    """
    Example 2: Merge JSON files with flat structure (better for pivot tables)
    """
    print("\n" + "="*60)
    print("Example 2: Merge with flat structure")
    print("="*60)
    
    json_folder = "JSON FILES"
    
    converter = JSONMergerExcelConverter(
        json_folder=json_folder,
        output_file="merged_output_flat.xlsx"
    )
    
    # Process with flat structure (all data in one sheet as rows)
    converter.process(use_flat=True)


def example_3_merge_specific_files():
    """
    Example 3: Custom merging of specific JSON files
    """
    print("\n" + "="*60)
    print("Example 3: Custom merge of specific files")
    print("="*60)
    
    converter = JSONMergerExcelConverter(
        json_folder=".",
        output_file="custom_merged.xlsx"
    )
    
    # Manually load specific files
    import json
    
    merged_data = {}
    
    # Add resultData.json
    if os.path.exists("resultData.json"):
        with open("resultData.json", 'r', encoding='utf-8') as f:
            merged_data.update(json.load(f))
        print("✓ Loaded resultData.json")
    
    # Add asinsdata.json
    if os.path.exists("asinsdata.json"):
        with open("asinsdata.json", 'r', encoding='utf-8') as f:
            asinsdata = json.load(f)
            # Merge intelligently
            for key, value in asinsdata.items():
                if key in merged_data:
                    if isinstance(merged_data[key], list) and isinstance(value, list):
                        merged_data[key].extend(value)
                else:
                    merged_data[key] = value
        print("✓ Loaded asinsdata.json")
    
    # Convert to Excel
    print("Converting to Excel...")
    converter.merged_data = merged_data
    converter.convert_to_excel_nested(merged_data)


def example_4_merge_current_directory():
    """
    Example 4: Merge all JSON files in current directory
    """
    print("\n" + "="*60)
    print("Example 4: Merge current directory JSON files")
    print("="*60)
    
    converter = JSONMergerExcelConverter(
        json_folder=".",  # Current directory
        output_file="merged_all.xlsx"
    )
    
    converter.process(use_flat=False)


if __name__ == "__main__":
    # Run examples
    
    # Uncomment the example you want to run:
    
    # Example 1: Nested structure (separate sheet per product)
    example_1_merge_json_files_in_folder()
    
    # Example 2: Flat structure (all data in one table)
    # example_2_merge_with_flat_structure()
    
    # Example 3: Custom specific files
    # example_3_merge_specific_files()
    
    # Example 4: Current directory
    # example_4_merge_current_directory()
