"""
Free OCR Module for Medicine Strip Recognition
Uses Tesseract, EasyOCR and PaddleOCR as free alternatives to Google Vision API
No API keys or billing required!
"""

import logging
import re
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Try to import OCR libraries
EASYOCR_AVAILABLE = False
PADDLEOCR_AVAILABLE = False
TESSERACT_AVAILABLE = False

try:
    import pytesseract
    import os
    # Set Tesseract path for Windows
    if os.name == 'nt':  # Windows
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logger.info(f"Tesseract OCR configured at: {tesseract_path}")
    TESSERACT_AVAILABLE = True
    logger.info("Tesseract OCR is available")
except ImportError:
    logger.warning("Tesseract not available. Install with: pip install pytesseract")

try:
    import easyocr
    import numpy as np
    EASYOCR_AVAILABLE = True
    logger.info("EasyOCR is available")
except ImportError:
    logger.warning("EasyOCR not available. Install with: pip install easyocr")

try:
    from paddleocr import PaddleOCR
    import numpy as np
    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR is available")
except ImportError:
    logger.warning("PaddleOCR not available. Install with: pip install paddleocr")


class FreeOCR:
    """Free OCR handler with multiple backend options"""
    
    def __init__(self):
        self.easyocr_reader = None
        self.paddleocr_reader = None
        
    def initialize_easyocr(self):
        """Initialize EasyOCR reader (lazy loading)"""
        if not EASYOCR_AVAILABLE:
            return False
        
        if self.easyocr_reader is None:
            try:
                logger.info("Initializing EasyOCR reader...")
                # Initialize with English language
                self.easyocr_reader = easyocr.Reader(['en'], gpu=False)
                logger.info("EasyOCR reader initialized successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR: {e}")
                return False
        return True
    
    def initialize_paddleocr(self):
        """Initialize PaddleOCR reader (lazy loading)"""
        if not PADDLEOCR_AVAILABLE:
            return False
        
        if self.paddleocr_reader is None:
            try:
                logger.info("Initializing PaddleOCR reader...")
                # Initialize with English language, disable GPU
                self.paddleocr_reader = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False, show_log=False)
                logger.info("PaddleOCR reader initialized successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")
                return False
        return True
    
    def extract_text_easyocr(self, image_content):
        """Extract text using EasyOCR"""
        try:
            if not EASYOCR_AVAILABLE:
                return None
                
            if not self.initialize_easyocr():
                return None
            
            logger.info("Processing image with EasyOCR...")
            
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_content))
            
            # Convert to numpy array
            import numpy as np
            img_array = np.array(image)
            
            # Perform OCR
            results = self.easyocr_reader.readtext(img_array)
            
            # Extract text from results
            extracted_text = []
            for (bbox, text, confidence) in results:
                if confidence > 0.3:  # Filter low confidence results
                    extracted_text.append(text)
                    logger.info(f"EasyOCR detected: '{text}' (confidence: {confidence:.2f})")
            
            full_text = ' '.join(extracted_text)
            logger.info(f"EasyOCR extracted text: {full_text}")
            return full_text
            
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            return None
    
    def extract_text_paddleocr(self, image_content):
        """Extract text using PaddleOCR"""
        try:
            if not PADDLEOCR_AVAILABLE:
                return None
                
            if not self.initialize_paddleocr():
                return None
            
            logger.info("Processing image with PaddleOCR...")
            
            # Convert bytes to PIL Image then to numpy array
            image = Image.open(io.BytesIO(image_content))
            import numpy as np
            img_array = np.array(image)
            
            # Perform OCR
            results = self.paddleocr_reader.ocr(img_array, cls=True)
            
            # Extract text from results
            extracted_text = []
            if results and results[0]:
                for line in results[0]:
                    if line and len(line) >= 2:
                        text = line[1][0]  # Get text
                        confidence = line[1][1]  # Get confidence
                        if confidence > 0.3:  # Filter low confidence results
                            extracted_text.append(text)
                            logger.info(f"PaddleOCR detected: '{text}' (confidence: {confidence:.2f})")
            
            full_text = ' '.join(extracted_text)
            logger.info(f"PaddleOCR extracted text: {full_text}")
            return full_text
            
        except Exception as e:
            logger.error(f"PaddleOCR extraction failed: {e}")
            return None
    
    def extract_text_tesseract(self, image_content):
        """Extract text using Tesseract OCR with image preprocessing"""
        try:
            if not TESSERACT_AVAILABLE:
                return None
            
            logger.info("Processing image with Tesseract...")
            
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_content))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Perform OCR with multiple configurations for better results
            try:
                # Try with default config first
                text = pytesseract.image_to_string(image, config='--psm 6')
                
                # If empty, try with different page segmentation mode
                if not text or len(text.strip()) < 10:
                    logger.info("Trying alternative Tesseract configuration...")
                    text = pytesseract.image_to_string(image, config='--psm 3')
                
                # If still empty, try with single block mode
                if not text or len(text.strip()) < 10:
                    logger.info("Trying single block mode...")
                    text = pytesseract.image_to_string(image, config='--psm 6 --oem 3')
                
                if text and len(text.strip()) > 0:
                    logger.info(f"Tesseract extracted {len(text)} characters")
                    logger.info(f"First 200 chars: {text[:200]}")
                    return text
                else:
                    logger.warning("Tesseract returned empty text")
                    return None
                    
            except pytesseract.TesseractNotFoundError:
                logger.error("Tesseract engine not found! Please install Tesseract OCR.")
                logger.error("Download from: https://github.com/UB-Mannheim/tesseract/wiki")
                logger.error("Or run: powershell -File setup_tesseract.ps1")
                return None
            
        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}", exc_info=True)
            return None
    
    def extract_text(self, image_content):
        """
        Extract text from image using available OCR engines
        Tries in order: Tesseract -> EasyOCR -> PaddleOCR
        """
        logger.info("Starting free OCR text extraction...")
        
        # Try Tesseract first (fastest and easiest to install)
        if TESSERACT_AVAILABLE:
            text = self.extract_text_tesseract(image_content)
            if text and len(text.strip()) > 0:
                return text
        
        # Try EasyOCR (best for medicine strips)
        if EASYOCR_AVAILABLE:
            text = self.extract_text_easyocr(image_content)
            if text:
                return text
        
        # Try PaddleOCR as fallback
        if PADDLEOCR_AVAILABLE:
            text = self.extract_text_paddleocr(image_content)
            if text:
                return text
        
        logger.error("All OCR methods failed or unavailable")
        return None


def extract_medicine_names_from_text(text, known_medicines=None):
    """
    Extract medicine names from OCR text
    Uses pattern matching and known medicine database
    """
    if not text:
        return []
    
    logger.info(f"Extracting medicine names from text: {text}")
    
    # Clean and normalize text
    text = text.upper()
    
    # Common medicine name patterns
    medicine_patterns = [
        r'\b[A-Z][a-z]+(?:ol|in|ine|ate|ide|one|cin|xin|zole|pril|sartan|statin)\b',
        r'\b(?:TAB|CAP|SYR|INJ|SUSP)\.?\s+([A-Z][A-Za-z]+)',
        r'\b([A-Z][A-Za-z]{3,})\s+\d+\s*(?:MG|ML|G)\b',
    ]
    
    found_medicines = []
    
    # Extract using patterns
    for pattern in medicine_patterns:
        matches = re.findall(pattern, text)
        found_medicines.extend(matches)
    
    # If known medicines list provided, match against it
    if known_medicines:
        for known_med in known_medicines:
            if known_med.upper() in text:
                found_medicines.append(known_med)
    
    # Remove duplicates and clean
    found_medicines = list(set([med.strip() for med in found_medicines if len(med.strip()) > 2]))
    
    logger.info(f"Extracted medicine names: {found_medicines}")
    return found_medicines


# Global OCR instance
_ocr_instance = None

def get_ocr_instance():
    """Get or create global OCR instance"""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = FreeOCR()
    return _ocr_instance


def extract_medicines_from_prescription_free(image_content, known_medicines=None):
    """
    Main function to extract medicines from prescription image
    Uses free OCR methods - no API keys required!
    
    Args:
        image_content: Image bytes
        known_medicines: Optional list of known medicine names for better matching
    
    Returns:
        List of medicine names found in the image
    """
    try:
        ocr = get_ocr_instance()
        
        # Extract text from image
        text = ocr.extract_text(image_content)
        
        if not text:
            logger.error("No text extracted from image")
            return []
        
        # Extract medicine names from text
        medicines = extract_medicine_names_from_text(text, known_medicines)
        
        return medicines
        
    except Exception as e:
        logger.error(f"Error in free OCR extraction: {e}", exc_info=True)
        return []
