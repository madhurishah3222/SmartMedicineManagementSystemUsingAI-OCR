"""
Quick test to verify the new patterns work for Olanzac and Bifilac strips
"""
import re

# Test patterns from app.py
PATTERNS = {
    'brand_name': [
        r"(?i)\b(OLANZAC|OMIZOLE|BIFILAC|BILAC|PARACETAMOL|DOLO|CROCIN|COMBIFLAM)\b",
        r"(?i)\b([A-Z][a-z]+(?:zole|zac|lac|flac|pril|olol|pine|mycin|cillin|floxacin))\b",
        r"(?i)\b([A-Z][A-Za-z]+)\s*&\s*([A-Z][A-Za-z]+)\b",
    ],
    'batch_number': [
        r"(?i)\b(?:B\.?\s*No\.?|Batch(?:\s*No\.?)?)\s*[:#-]?\s*([A-Z][0-9]{4,6})\b",
        r"(?i)\b(?:B\.?\s*No\.?|Batch(?:\s*No\.?)?)\s*[:#-]?\s*([A-Z]{2,4}[0-9]{2,4})\b",
    ],
    'mfd': [
        r"(?i)MFG\.?\s*DT\.?\s*([A-Z]{3}\.?\s*\d{2,4})",
        r"(?i)MFD\.?\s*(\d{1,2}[./-]\d{2,4})",
    ],
    'expiry': [
        r"(?i)EXP\.?\s*DT\.?\s*([A-Z]{3}\.?\s*\d{2,4})",
        r"(?i)EXP\.?\s*(\d{1,2}[./-]\d{2,4})",
    ],
    'mrp': [
        r"(?i)M\.?R\.?P\.?\s*Rs\.?\s*(\d+(?:\.\d{2})?)",
        r"(?i)M\.?R\.?P\.?Rs\.?\s*(\d+(?:\.\d{2})?)",
    ],
}

def test_pattern(pattern_list, text, expected):
    """Test if any pattern in the list matches the expected value"""
    for pattern in pattern_list:
        match = re.search(pattern, text)
        if match:
            result = match.group(1) if match.lastindex >= 1 else match.group(0)
            if expected.lower() in result.lower() or result.lower() in expected.lower():
                return True, result
    return False, None

# Test data
test_cases = [
    {
        'name': 'Olanzac Strip',
        'text': '''
        Olanzac & Omizole Tablets
        B.No. E40001
        MFG. DT. JAN.24 EXP. DT. DEC.26
        M.R.P. Rs. 189.00
        PER 10 TABLETS
        ''',
        'expected': {
            'brand_name': 'OLANZAC',
            'batch_number': 'E40001',
            'mfd': 'JAN.24',
            'expiry': 'DEC.26',
            'mrp': '189.00'
        }
    },
    {
        'name': 'Bifilac Strip',
        'text': '''
        BIFILAC Capsules
        B.No. ALA306
        MFD. 10/2023 EXP. 09/2025
        10 CAPS. M.R.P.Rs.140.00
        INCL.OF ALL TAXES
        ''',
        'expected': {
            'brand_name': 'BIFILAC',
            'batch_number': 'ALA306',
            'mfd': '10/2023',
            'expiry': '09/2025',
            'mrp': '140.00'
        }
    }
]

print("=" * 60)
print("PATTERN MATCHING TEST")
print("=" * 60)

all_passed = True

for test_case in test_cases:
    print(f"\n--- {test_case['name']} ---")
    text = test_case['text']
    expected = test_case['expected']
    
    for field, expected_value in expected.items():
        passed, result = test_pattern(PATTERNS[field], text, expected_value)
        status = "✓" if passed else "✗"
        print(f"{status} {field}: {result if result else 'NOT FOUND'} (expected: {expected_value})")
        if not passed:
            all_passed = False

print("\n" + "=" * 60)
if all_passed:
    print("✓ ALL TESTS PASSED!")
    print("\nThe patterns are working correctly.")
    print("Now test with real images in the Flask app.")
else:
    print("✗ SOME TESTS FAILED")
    print("\nReview the patterns in app.py")

print("=" * 60)
