"""
Test script for real medicine strips (Olanzac and Bifilac)
"""
import sys
import os

# Add the main app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'main medicine_ocr updated'))

def test_strip_patterns():
    """Test pattern matching with real strip data"""
    print("=" * 60)
    print("TEST: Real Medicine Strip Pattern Matching")
    print("=" * 60)
    
    try:
        from advanced_strip_ocr import AdvancedStripOCR
        
        ocr = AdvancedStripOCR()
        
        # Test Strip 1: Olanzac
        print("\n--- Strip 1: Olanzac ---")
        test_text_1 = """
        OLANZAC & OMIZOLE
        B.No. E40001
        MFG. DT. JAN.24 EXP. DT. DEC.26
        M.R.P. Rs. 189.00
        PER 10 TABLETS
        """
        
        info1 = ocr.extract_medicine_info(test_text_1)
        print(f"Medicine Name: {info1.get('medicine_name', 'NOT FOUND')}")
        print(f"Batch Number: {info1.get('batch_number', 'NOT FOUND')}")
        print(f"MFG Date: {info1.get('manufacture_date', 'NOT FOUND')}")
        print(f"EXP Date: {info1.get('expiry_date', 'NOT FOUND')}")
        print(f"MRP: {info1.get('mrp', 'NOT FOUND')}")
        
        # Validate Strip 1
        strip1_pass = (
            info1.get('batch_number') == 'E40001' and
            info1.get('mrp') == 189.0
        )
        
        if strip1_pass:
            print("✓ Strip 1: PASS")
        else:
            print("✗ Strip 1: FAIL")
        
        # Test Strip 2: Bifilac
        print("\n--- Strip 2: Bifilac ---")
        test_text_2 = """
        BIFILAC
        B.No. ALA306
        MFD. 10/2023 EXP. 09/2025
        10 CAPS. M.R.P.Rs.140.00
        INCL.OF ALL TAXES
        """
        
        info2 = ocr.extract_medicine_info(test_text_2)
        print(f"Medicine Name: {info2.get('medicine_name', 'NOT FOUND')}")
        print(f"Batch Number: {info2.get('batch_number', 'NOT FOUND')}")
        print(f"MFG Date: {info2.get('manufacture_date', 'NOT FOUND')}")
        print(f"EXP Date: {info2.get('expiry_date', 'NOT FOUND')}")
        print(f"MRP: {info2.get('mrp', 'NOT FOUND')}")
        
        # Validate Strip 2
        strip2_pass = (
            'BIFILAC' in str(info2.get('medicine_name', '')).upper() and
            info2.get('batch_number') == 'ALA306' and
            info2.get('mrp') == 140.0
        )
        
        if strip2_pass:
            print("✓ Strip 2: PASS")
        else:
            print("✗ Strip 2: FAIL")
        
        # Overall result
        print("\n" + "=" * 60)
        if strip1_pass and strip2_pass:
            print("✓ ALL TESTS PASSED!")
            print("The patterns are correctly configured for these strips.")
            return True
        else:
            print("✗ SOME TESTS FAILED")
            print("Review the output above for details.")
            return False
            
    except Exception as e:
        print(f"✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_date_parsing():
    """Test date parsing with real formats"""
    print("\n" + "=" * 60)
    print("TEST: Date Parsing for Real Strips")
    print("=" * 60)
    
    try:
        from advanced_strip_ocr import AdvancedStripOCR
        
        ocr = AdvancedStripOCR()
        
        test_dates = [
            ("JAN.24", "01/2024"),
            ("DEC.26", "12/2026"),
            ("10/2023", "10/2023"),
            ("09/2025", "09/2025"),
        ]
        
        all_pass = True
        for input_date, expected in test_dates:
            result = ocr._parse_date(input_date)
            status = "✓" if result == expected else "✗"
            print(f"{status} '{input_date}' -> '{result}' (expected: '{expected}')")
            if result != expected:
                all_pass = False
        
        print("\n" + "=" * 60)
        if all_pass:
            print("✓ ALL DATE PARSING TESTS PASSED!")
            return True
        else:
            print("✗ SOME DATE PARSING TESTS FAILED")
            return False
            
    except Exception as e:
        print(f"✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_batch_patterns():
    """Test batch number patterns"""
    print("\n" + "=" * 60)
    print("TEST: Batch Number Patterns")
    print("=" * 60)
    
    try:
        from advanced_strip_ocr import AdvancedStripOCR
        import re
        
        ocr = AdvancedStripOCR()
        
        test_batches = [
            ("B.No. E40001", "E40001"),
            ("B.No. ALA306", "ALA306"),
            ("BATCH NO: ABC123", "ABC123"),
            ("LOT NO: XYZ789", "XYZ789"),
        ]
        
        all_pass = True
        for text, expected in test_batches:
            info = ocr.extract_medicine_info(text)
            result = info.get('batch_number', 'NOT FOUND')
            status = "✓" if result == expected else "✗"
            print(f"{status} '{text}' -> '{result}' (expected: '{expected}')")
            if result != expected:
                all_pass = False
        
        print("\n" + "=" * 60)
        if all_pass:
            print("✓ ALL BATCH PATTERN TESTS PASSED!")
            return True
        else:
            print("✗ SOME BATCH PATTERN TESTS FAILED")
            return False
            
    except Exception as e:
        print(f"✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("REAL MEDICINE STRIP TESTING")
    print("Testing patterns for Olanzac and Bifilac strips")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Pattern Matching", test_strip_patterns()))
    results.append(("Date Parsing", test_date_parsing()))
    results.append(("Batch Patterns", test_batch_patterns()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Ready to process real strips.")
        print("\nNext steps:")
        print("1. Start the Flask app")
        print("2. Upload the Olanzac and Bifilac strip images")
        print("3. Verify the extracted data matches:")
        print("   - Olanzac: E40001, JAN.24, DEC.26, Rs.189.00")
        print("   - Bifilac: ALA306, 10/2023, 09/2025, Rs.140.00")
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Review the output above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
