"""
Test script specifically for BIFILAC strip OCR issues
"""
import sys
import os

# Add the main app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'main medicine_ocr updated'))

def test_bifilac_patterns():
    """Test pattern matching specifically for BIFILAC strip"""
    print("=" * 60)
    print("BIFILAC STRIP PATTERN TEST")
    print("=" * 60)
    
    try:
        from advanced_strip_ocr import AdvancedStripOCR
        
        ocr = AdvancedStripOCR()
        
        # Test with the exact text that should be extracted from BIFILAC strip
        bifilac_text = """
        BIFILAC
        Lactic Acid Bacillus
        B.No. ALA306
        MFD. 10/2023 EXP. 09/2025
        10 CAPS. M.R.P.Rs.140.00
        INCL.OF ALL TAXES
        """
        
        print("Testing BIFILAC text extraction:")
        print("Input text:")
        print(bifilac_text)
        print("\n" + "-" * 40)
        
        info = ocr.extract_medicine_info(bifilac_text)
        
        print("Extracted Information:")
        print(f"Medicine Name: {info.get('medicine_name', 'NOT FOUND')}")
        print(f"Batch Number: {info.get('batch_number', 'NOT FOUND')}")
        print(f"MFG Date: {info.get('manufacture_date', 'NOT FOUND')}")
        print(f"EXP Date: {info.get('expiry_date', 'NOT FOUND')}")
        print(f"MRP: {info.get('mrp', 'NOT FOUND')}")
        
        # Check if results are correct
        expected = {
            'medicine_name': 'BIFILAC',
            'batch_number': 'ALA306',
            'manufacture_date': '10/2023',
            'expiry_date': '09/2025',
            'mrp': 140.0
        }
        
        print("\n" + "-" * 40)
        print("VALIDATION:")
        
        all_correct = True
        for field, expected_value in expected.items():
            actual_value = info.get(field)
            if field == 'medicine_name':
                correct = expected_value.upper() in str(actual_value).upper() if actual_value else False
            elif field == 'mrp':
                correct = abs(float(actual_value or 0) - expected_value) < 0.01
            else:
                correct = str(actual_value) == str(expected_value)
            
            status = "✓" if correct else "✗"
            print(f"{status} {field}: {actual_value} (expected: {expected_value})")
            
            if not correct:
                all_correct = False
        
        print("\n" + "=" * 60)
        if all_correct:
            print("✓ ALL BIFILAC PATTERNS WORKING CORRECTLY!")
        else:
            print("✗ BIFILAC PATTERNS NEED FIXING")
            
        return all_correct
        
    except Exception as e:
        print(f"✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bifilac_patterns()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")