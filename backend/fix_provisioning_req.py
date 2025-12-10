#!/usr/bin/env python3
"""Fix ProvisioningRequirements usage in all test files."""
import re
from pathlib import Path

def fix_provisioning_requirements(content: str) -> str:
    """Fix ProvisioningRequirements instantiations."""
    
    # Replace field names
    replacements = {
        'session_loading_needed=': 'needs_session=',
        'warmup_days=0,': '',  # Remove
        'warmup_days=\\d+,': '',  # Remove with any number
        ', warmup_days=0': '',  # Remove at different positions
        ', warmup_days=\\d+': '',
        'interval=None,': '',  # Remove
        'interval="[^"]*",': '',  # Remove with any value
        ', interval=None': '',
        ', interval="[^"]*"': '',
        'days=None,': '',  # Remove
        'days=\\d+,': '',  # Remove with number
        ', days=None': '',
        ', days=\\d+': '',
        'historical_only=False,': '',  # Remove
        'historical_only=True,': '',  # Remove
        ', historical_only=False': '',
        ', historical_only=True': '',
    }
    
    fixed = content
    for old, new in replacements.items():
        fixed = re.sub(old, new, fixed)
    
    # Add needs_historical if historical_days > 0 and needs_historical not present
    def add_needs_historical(match):
        content = match.group(1)
        if 'historical_days=' in content and 'needs_historical' not in content:
            # Insert needs_historical=True before historical_days
            content = content.replace('historical_days=', 'needs_historical=True,\n            historical_days=', 1)
        return f'ProvisioningRequirements({content})'
    
    fixed = re.sub(r'ProvisioningRequirements\s*\((.*?)\)', add_needs_historical, fixed, flags=re.DOTALL)
    
    # Clean up multiple consecutive commas and trailing commas before closing paren
    fixed = re.sub(r',\s*,', ',', fixed)
    fixed = re.sub(r',\s*\)', ')', fixed)
    
    return fixed


def main():
    test_dir = Path(__file__).parent / 'tests'
    
    # Find all test files
    test_files = list(test_dir.rglob('test_*.py'))
    
    fixed_count = 0
    for test_file in test_files:
        content = test_file.read_text()
        
        if 'ProvisioningRequirements(' in content:
            print(f"Fixing {test_file}")
            fixed_content = fix_provisioning_requirements(content)
            test_file.write_text(fixed_content)
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == '__main__':
    main()
