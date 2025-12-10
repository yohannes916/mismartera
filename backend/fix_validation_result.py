#!/usr/bin/env python3
"""Fix SymbolValidationResult usage in all test files."""
import re
from pathlib import Path

def fix_validation_result(content: str) -> str:
    """Fix SymbolValidationResult instantiations."""
    
    # Pattern to match SymbolValidationResult(...) calls
    pattern = r'SymbolValidationResult\s*\((.*?)\)'
    
    def replace_fields(match):
        args = match.group(1)
        
        # Replace field names
        args = args.replace('has_data_source=', 'data_source_available=')
        args = args.replace('has_sufficient_historical=', 'has_historical_data=')
        
        # Remove has_parquet_data lines (doesn't exist in real implementation)
        lines = args.split('\n')
        filtered_lines = []
        for line in lines:
            if 'has_parquet_data=' not in line:
                filtered_lines.append(line)
        args = '\n'.join(filtered_lines)
        
        # Add symbol field if not present (required field)
        if 'symbol=' not in args and 'can_proceed' in args:
            # Insert symbol as first argument
            if args.strip().startswith('can_proceed'):
                args = 'symbol="TEST",\n            ' + args
        
        return f'SymbolValidationResult({args})'
    
    # Apply replacements
    fixed = re.sub(pattern, replace_fields, content, flags=re.DOTALL)
    return fixed


def main():
    test_dir = Path(__file__).parent / 'tests'
    
    # Find all test files
    test_files = list(test_dir.rglob('test_*.py'))
    
    fixed_count = 0
    for test_file in test_files:
        content = test_file.read_text()
        
        if 'SymbolValidationResult(' in content:
            print(f"Fixing {test_file}")
            fixed_content = fix_validation_result(content)
            test_file.write_text(fixed_content)
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == '__main__':
    main()
