"""
Advanced Medicine Strip OCR Module (Lite Version)
Works without OpenCV - uses only PIL and existing libraries
Specialized for handling challenging medicine strip images
"""

import logging
import re
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import OCR libraries
TESSERACT_AVAILABLE = False
EASYOCR_AVAILABLE = False

try:
    import pytesseract
    import os
    if os.name == 'nt':  # Windows
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    TESSERACT_AVAILABLE = True
    logger.info("Tesseract OCR available")
except ImportError:
    logger.warning("Tesseract not available")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
    logger.info("EasyOCR available")
except ImportError:
    logger.warning("EasyOCR not available")


class AdvancedStripOCRLite:
    """Advanced OCR for challenging medicine strip images (Lite version without OpenCV)"""
    
    def __init__(self):
        self.easyocr_reader = None
        
    def initialize_easyocr(self):
        """Initialize EasyOCR reader"""
        if not EASYOCR_AVAILABLE or self.easyocr_reader is not None:
            return self.easyocr_reader is not None
        
        try:
            logger.info("Initializing EasyOCR...")
            self.easyocr_reader = easyocr.Reader(['en'], gpu=False)
            logger.info("EasyOCR initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}")
            return False
    
    def enhance_image_aggressive(self, image):
        """Aggressively enhance image for better OCR"""
        try:
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Upscale significantly for better text recognition
            width, height = image.size
            if width < 3000 or height < 3000:
                scale = max(3000 / width, 3000 / height)
                new_size = (int(width * scale), int(height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Upscaled to {new_size}")
            
            # Very aggressive contrast enhancement
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(4.0)
            
            # Very aggressive sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(4.0)
            
            # Brightness adjustment
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.4)
            
            # Apply unsharp mask for extra sharpness
            image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
            
            return image
        except Exception as e:
            logger.error(f"Enhancement failed: {e}")
            return image
    
    def preprocess_grayscale_threshold(self, image):
        """Convert to grayscale with adaptive thresholding"""
        try:
            # Convert to grayscale
            gray = image.convert('L')
            
            # Auto contrast
            gray = ImageOps.autocontrast(gray, cutoff=3)
            
            # Apply threshold
            threshold = 128
            binary = gray.point(lambda p: 255 if p > threshold else 0)
            
            return binary
        except Exception as e:
            logger.error(f"Grayscale preprocessing failed: {e}")
            return image
    
    def preprocess_edge_enhance(self, image):
        """Enhance edges for embossed text"""
        try:
            # Convert to grayscale
            gray = image.convert('L')
            
            # Find edges
            edges = gray.filter(ImageFilter.FIND_EDGES)
            
            # Enhance edges
            edges = ImageEnhance.Contrast(edges).enhance(2.0)
            
            # Combine with original
            from PIL import ImageChops
            combined = ImageChops.add(gray, edges, scale=1.5)
            
            return combined
        except Exception as e:
            logger.error(f"Edge enhancement failed: {e}")
            return image
    
    def preprocess_denoise(self, image):
        """Reduce noise while preserving text"""
        try:
            # Convert to grayscale
            gray = image.convert('L')
            
            # Apply median filter to reduce noise
            denoised = gray.filter(ImageFilter.MedianFilter(size=3))
            
            # Sharpen
            sharpened = denoised.filter(ImageFilter.SHARPEN)
            
            # Enhance contrast
            enhanced = ImageEnhance.Contrast(sharpened).enhance(2.5)
            
            return enhanced
        except Exception as e:
            logger.error(f"Denoising failed: {e}")
            return image
    
    def try_rotations(self, image):
        """Try OCR with different rotations - DISABLED for speed without EasyOCR"""
        # Skip rotations when only Tesseract is available (too slow)
        if not EASYOCR_AVAILABLE:
            logger.info("Skipping rotations (EasyOCR not available)")
            return None
        
        results = []
        
        # Try original orientation
        text = self._ocr_image(image, "Rotation 0°")
        if text:
            results.append(text)
        
        # Try 90 degree rotation
        rotated_90 = image.rotate(90, expand=True)
        text = self._ocr_image(rotated_90, "Rotation 90°")
        if text:
            results.append(text)
        
        return ' '.join(results) if results else None
    
    def extract_text_multiple_methods(self, image_content):
        """Extract text using multiple preprocessing methods"""
        all_text = []
        
        try:
            # Load original image
            original = Image.open(io.BytesIO(image_content))
            
            # Convert to RGB if needed
            if original.mode != 'RGB':
                original = original.convert('RGB')
            
            # If EasyOCR not available, use only 2 fastest methods
            if not EASYOCR_AVAILABLE:
                logger.info("EasyOCR not available - using fast mode (2 methods only)")
                
                # Method 1: Aggressive enhancement (best for Tesseract)
                logger.info("Method 1: Aggressive enhancement...")
                enhanced = self.enhance_image_aggressive(original.copy())
                text1 = self._ocr_image(enhanced, "Method 1")
                if text1:
                    all_text.append(text1)
                
                # Method 2: Grayscale with threshold
                logger.info("Method 2: Grayscale threshold...")
                gray_thresh = self.preprocess_grayscale_threshold(original.copy())
                text2 = self._ocr_image(gray_thresh, "Method 2")
                if text2:
                    all_text.append(text2)
                
                # Combine and return
                combined = '\n'.join(all_text)
                logger.info(f"Total text extracted: {len(combined)} characters from {len(all_text)} methods")
                return combined if combined else None
            
            # Full processing with EasyOCR
            logger.info("EasyOCR available - using full mode (6 methods)")
            
            # Method 1: Aggressive enhancement
            logger.info("Method 1: Aggressive enhancement...")
            enhanced = self.enhance_image_aggressive(original.copy())
            text1 = self._ocr_image(enhanced, "Method 1")
            if text1:
                all_text.append(text1)
            
            # Method 2: Grayscale with threshold
            logger.info("Method 2: Grayscale threshold...")
            gray_thresh = self.preprocess_grayscale_threshold(original.copy())
            text2 = self._ocr_image(gray_thresh, "Method 2")
            if text2:
                all_text.append(text2)
            
            # Method 3: Edge enhancement
            logger.info("Method 3: Edge enhancement...")
            edges = self.preprocess_edge_enhance(original.copy())
            text3 = self._ocr_image(edges, "Method 3")
            if text3:
                all_text.append(text3)
            
            # Method 4: Denoising
            logger.info("Method 4: Denoising...")
            denoised = self.preprocess_denoise(original.copy())
            text4 = self._ocr_image(denoised, "Method 4")
            if text4:
                all_text.append(text4)
            
            # Method 5: Original with basic enhancement
            logger.info("Method 5: Basic enhancement...")
            basic = ImageEnhance.Contrast(original.copy()).enhance(2.0)
            text5 = self._ocr_image(basic, "Method 5")
            if text5:
                all_text.append(text5)
            
            # Method 6: Try different rotations on best enhanced image
            logger.info("Method 6: Trying rotations...")
            text6 = self.try_rotations(enhanced)
            if text6:
                all_text.append(text6)
            
            # Combine all extracted text
            combined = '\n'.join(all_text)
            logger.info(f"Total text extracted: {len(combined)} characters from {len(all_text)} methods")
            
            return combined if combined else None
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return None
    
    def _ocr_image(self, image, method_name=""):
        """Perform OCR on preprocessed image"""
        text_results = []
        
        # Try EasyOCR first (better for medicine strips)
        if EASYOCR_AVAILABLE:
            try:
                if self.initialize_easyocr():
                    # Convert PIL to numpy array for EasyOCR
                    import numpy as np
                    img_array = np.array(image)
                    results = self.easyocr_reader.readtext(img_array, detail=1, paragraph=False)
                    
                    for (bbox, text, confidence) in results:
                        if confidence > 0.15:  # Very low threshold for challenging images
                            text_results.append(text)
                            logger.info(f"{method_name} EasyOCR: '{text}' (conf: {confidence:.2f})")
            except Exception as e:
                logger.error(f"EasyOCR failed for {method_name}: {e}")
        
        # Try Tesseract with multiple PSM modes
        if TESSERACT_AVAILABLE:
            psm_modes = [6, 11, 12, 3, 4]  # Different page segmentation modes
            for psm in psm_modes:
                try:
                    config = f'--psm {psm} --oem 3'
                    text = pytesseract.image_to_string(image, config=config)
                    if text and len(text.strip()) > 5:
                        text_results.append(text)
                        logger.info(f"{method_name} Tesseract PSM{psm}: extracted {len(text)} chars")
                        break  # Use first successful result
                except Exception as e:
                    continue
        
        return ' '.join(text_results) if text_results else None
    
    def extract_medicine_info(self, text):
        """Extract structured medicine information from text"""
        if not text:
            return {}
        
        text_upper = text.upper()
        info = {}
        
        # Split text into lines for better context-aware extraction
        lines = text_upper.split('\n')
        
        # Extract medicine name - look for prominent brand names
        name_patterns = [
            # Common medicine suffixes (most reliable)
            r'\b([A-Z][a-z]+(?:zole|pril|olol|pine|mycin|cillin|floxacin|mab|nib|tinib|pam|dine|done))\b',
            # Brand names with modifiers (like RABEMI-DSR)
            r'\b([A-Z]{3,}(?:-[A-Z]{2,})?)\s+(?:SODIUM|EC|SR|DSR|XR|CR|MR)\b',
            # All caps brand names (4+ letters, not common words)
            r'\b([A-Z]{4,}(?:-[A-Z]+)?)\b',
        ]
        
        # Extensive exclude list
        exclude = [
            'MFG', 'MFD', 'EXP', 'EXPIRY', 'MRP', 'BATCH', 'LOT', 'CAPS', 'TABLETS', 'CAPSULES',
            'THE', 'AND', 'FOR', 'USE', 'ONLY', 'NOT', 'STORE', 'KEEP', 'AWAY', 'FROM', 'CHILDREN',
            'DATE', 'PRICE', 'PACK', 'SIZE', 'STRIP', 'EACH', 'CONTAINS', 'COMPOSITION', 'COLOUR',
            'PELLETS', 'COATED', 'RELEASE', 'HARD', 'GELATIN', 'SHELL', 'SHELLS', 'EXCIPIENTS',
            'MANUFACTURED', 'MANUFACTURER', 'STORAGE', 'DIRECTIONS', 'PHYSICIAN', 'DOCTOR',
            'INCL', 'TAXES', 'REGISTERED', 'TRADEMARK', 'LIMITED', 'PHARMA', 'PHARMACEUTICALS',
            'CERTIFIED', 'LICENSE', 'PLOT', 'SECTOR', 'INDIA', 'INDIAN', 'COMPANY', 'COMPANIES',
            'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER',
            'OCTOBER', 'NOVEMBER', 'DECEMBER', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
            'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'PERAUTABLETS', 'PAS', 'TABLETS'
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, text)
            if matches:
                for match in matches:
                    match_upper = match.upper()
                    # Filter out excluded words and short matches
                    if match_upper not in exclude and len(match) >= 4:
                        # Prefer matches that appear in first 300 chars (likely brand name)
                        if match in text[:300]:
                            # Additional validation: not just numbers
                            if not match.isdigit():
                                info['medicine_name'] = match
                                logger.info(f"Found medicine name: {match}")
                                break
                if 'medicine_name' in info:
                    break
        
        # Extract batch number - VERY specific patterns only
        batch_patterns = [
            # Most specific: B.No. followed by code
            r'B\.?\s*NO\.?\s*([A-Z]{2,4}[0-9]{4,6})\b',  # B.No. ALA306, E40001
            r'B\.?\s*NO\.?\s*([0-9]{4,6}[A-Z]{2,4})\b',  # B.No. 40001E
            # BATCH followed by code
            r'BATCH\.?\s*NO\.?\s*([A-Z]{2,4}[0-9]{4,6})\b',
            r'BATCH\s*[:\-]\s*([A-Z]{2,4}[0-9]{4,6})\b',
            # LOT followed by code
            r'LOT\.?\s*NO\.?\s*([A-Z]{2,4}[0-9]{4,6})\b',
            r'LOT\s*[:\-]\s*([A-Z]{2,4}[0-9]{4,6})\b',
        ]
        
        for pattern in batch_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                for match in matches:
                    # Strict validation
                    if (re.search(r'[A-Z]', match) and 
                        re.search(r'[0-9]', match) and 
                        5 <= len(match) <= 10):
                        # Exclude common false positives
                        exclude_patterns = [
                            r'^[0-9]{2}[/-][0-9]{4}$',  # Dates
                            r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)',  # Month names
                            r'^[0-9]+$',  # Only numbers
                            r'^[A-Z]+$',  # Only letters
                        ]
                        is_valid = True
                        for exclude in exclude_patterns:
                            if re.match(exclude, match):
                                is_valid = False
                                break
                        
                        if is_valid:
                            info['batch_number'] = match
                            logger.info(f"Found batch number: {match}")
                            break
                if 'batch_number' in info:
                    break
        
        # Extract MFG date - prioritize specific formats (handle both JAN.24 and 10/2023 formats)
        mfg_patterns = [
            # Most specific patterns first (from stamp area)
            r'MFG\.?\s*DT\.?\s*([A-Z]{3}\.?[0-9]{2})\b',  # MFG. DT. JAN.24
            r'MFG\.?\s*DT\.?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # MFG. DT. 01/2024
            r'MFG\.?\s*DT\.?\s*([0-9]{1,2}[\/\-][0-9]{2})',  # MFG. DT. 01/24
            r'MFD\.?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # MFD. 10/2023
            # Standard formats
            r'MFG\.?\s*[:\-]?\s*([A-Z]{3}\.?[0-9]{2})\b',  # MFG: JAN.24
            r'MFG\.?\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # MFG: 10/2023
            r'MFD\.?\s*[:\-]?\s*([A-Z]{3}\.?[0-9]{2})\b',  # MFD: JAN.24
            r'MFD\.?\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # MFD: 10/2023
        ]
        
        for pattern in mfg_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                for match in matches:
                    parsed = self._parse_date(match)
                    # Validate: MFG date should be recent (2020-2025)
                    if parsed and '202' in parsed:
                        year = int(parsed.split('/')[-1])
                        if 2020 <= year <= 2025:
                            info['manufacture_date'] = parsed
                            break
                if 'manufacture_date' in info:
                    break
        
        # Extract EXP date - prioritize specific formats (handle both DEC.26 and 09/2025 formats)
        exp_patterns = [
            # Most specific patterns first (from stamp area)
            r'EXP\.?\s*DT\.?\s*([A-Z]{3}\.?[0-9]{2})\b',  # EXP. DT. DEC.26
            r'EXP\.?\s*DT\.?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # EXP. DT. 09/2025
            r'EXP\.?\s*DT\.?\s*([0-9]{1,2}[\/\-][0-9]{2})',  # EXP. DT. 09/25
            r'EXP\.?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # EXP. 09/2025
            # Standard formats
            r'EXP\.?\s*[:\-]?\s*([A-Z]{3}\.?[0-9]{2})\b',  # EXP: DEC.26
            r'EXP\.?\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # EXP: 09/2025
            r'EXPIRY\.?\s*[:\-]?\s*([A-Z]{3}\.?[0-9]{2})\b',  # EXPIRY: DEC.26
            r'EXPIRY\.?\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{4})',  # EXPIRY: 09/2025
        ]
        
        for pattern in exp_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                for match in matches:
                    parsed = self._parse_date(match)
                    # Validate: EXP date should be future (2024-2030)
                    if parsed and '20' in parsed:
                        year = int(parsed.split('/')[-1])
                        if 2024 <= year <= 2030:
                            info['expiry_date'] = parsed
                            break
                if 'expiry_date' in info:
                    break
        
        # Extract MRP - VERY specific to avoid license numbers
        mrp_patterns = [
            # Most specific: M.R.P. Rs. followed by 2-4 digit number
            r'M\.?R\.?P\.?\s*RS\.?\s*([0-9]{2,3}\.?[0-9]{0,2})\b',  # M.R.P. Rs. 169.00
            r'M\.?R\.?P\.?\s*₹\s*([0-9]{2,3}\.?[0-9]{0,2})\b',  # M.R.P. ₹ 169.00
            # MRP Rs. (without dots)
            r'MRP\s+RS\.?\s*([0-9]{2,3}\.?[0-9]{0,2})\b',  # MRP Rs. 140
            r'MRP\s+₹\s*([0-9]{2,3}\.?[0-9]{0,2})\b',  # MRP ₹ 140
        ]
        
        for pattern in mrp_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                for match in matches:
                    try:
                        # Remove any spaces or commas
                        clean_match = match.replace(',', '').replace(' ', '').strip()
                        price = float(clean_match)
                        
                        # VERY strict validation: medicine prices are 10-999 Rs (3 digits max)
                        if 10 <= price <= 999:
                            info['mrp'] = price
                            logger.info(f"Found MRP: Rs. {price}")
                            break
                    except ValueError:
                        continue
                if 'mrp' in info:
                    break
        
        logger.info(f"Extracted info: {info}")
        logger.info(f"Text sample for debugging: {text_upper[:500]}")
        return info
    
    def _parse_date(self, date_str):
        """Parse date string to standard format"""
        try:
            date_str = date_str.strip().upper().replace('.', '')
            
            # Month mapping
            months = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            # Try MM/YYYY or MM-YYYY
            if '/' in date_str or '-' in date_str:
                parts = re.split(r'[\/\-]', date_str)
                if len(parts) == 2:
                    try:
                        month, year = int(parts[0]), int(parts[1])
                        # Handle 2-digit year
                        if year < 100:
                            year = 2000 + year
                        return datetime(year, month, 1).strftime('%m/%Y')
                    except:
                        pass
            
            # Try MON.YY or MONYY format (e.g., JAN24, JAN.24)
            for month_name, month_num in months.items():
                if month_name in date_str:
                    # Extract year (2 or 4 digits)
                    year_match = re.search(r'[0-9]{2,4}', date_str)
                    if year_match:
                        year = int(year_match.group())
                        # Convert 2-digit year to 4-digit
                        if year < 100:
                            # Assume 20-49 = 2020-2049, 50-99 = 1950-1999
                            year = 2000 + year if year < 50 else 1900 + year
                        
                        # Validate year range (2020-2030 for medicines)
                        if 2020 <= year <= 2030:
                            return datetime(year, month_num, 1).strftime('%m/%Y')
            
            return None
        except Exception as e:
            logger.error(f"Date parsing failed for '{date_str}': {e}")
            return None
    
    def extract_from_bottom_area(self, image_content):
        """Extract text specifically from bottom 30% of image (where stamps usually are)"""
        try:
            from PIL import Image
            import io
            
            image = Image.open(io.BytesIO(image_content))
            width, height = image.size
            
            # Crop bottom 30% of image
            bottom_crop = image.crop((0, int(height * 0.7), width, height))
            
            # Enhance the cropped area
            bottom_enhanced = self.enhance_image_aggressive(bottom_crop)
            
            # Extract text from bottom area
            text = self._ocr_image(bottom_enhanced, "Bottom Area")
            
            return text if text else ""
        except Exception as e:
            logger.error(f"Bottom area extraction failed: {e}")
            return ""
    
    def process_medicine_strip(self, image_content):
        """Main method to process medicine strip image"""
        logger.info("Starting advanced medicine strip OCR (Lite)...")
        
        # Skip bottom area extraction if EasyOCR not available (too slow with Tesseract)
        bottom_text = ""
        if EASYOCR_AVAILABLE:
            # Extract text from bottom area first (priority for batch/dates/MRP)
            bottom_text = self.extract_from_bottom_area(image_content)
            logger.info(f"Bottom area text: {bottom_text[:200] if bottom_text else 'None'}")
        else:
            logger.info("Skipping bottom area extraction (EasyOCR not available)")
        
        # Extract text using multiple methods from full image
        full_text = self.extract_text_multiple_methods(image_content)
        
        if not full_text and not bottom_text:
            logger.warning("No text extracted from image")
            return None
        
        # Combine texts, prioritizing bottom area
        combined_text = (bottom_text + '\n' + full_text) if bottom_text else full_text
        
        # Extract structured information
        info = self.extract_medicine_info(combined_text)
        info['raw_text'] = combined_text
        
        return info


# Global instance
_advanced_ocr_lite = None

def get_advanced_ocr():
    """Get or create advanced OCR instance"""
    global _advanced_ocr_lite
    if _advanced_ocr_lite is None:
        _advanced_ocr_lite = AdvancedStripOCRLite()
    return _advanced_ocr_lite


def process_medicine_strip_image(image_content):
    """Process medicine strip image and extract information"""
    ocr = get_advanced_ocr()
    return ocr.process_medicine_strip(image_content)
