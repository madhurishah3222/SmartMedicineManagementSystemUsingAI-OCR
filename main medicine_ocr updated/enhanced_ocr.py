"""
Enhanced OCR Module for Medicine Strip Recognition
Specialized for extracting: Batch No, MFG Date, EXP Date, MRP
"""

import re
import logging
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
import io

logger = logging.getLogger(__name__)

class EnhancedMedicineOCR:
    """Enhanced OCR specifically for medicine strip information extraction"""
    
    def __init__(self):
        self.tesseract_available = False
        try:
            import pytesseract
            import os
            if os.name == 'nt':
                tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                if os.path.exists(tesseract_path):
                    pytesseract.pytesseract.tesseract_cmd = tesseract_path
            self.pytesseract = pytesseract
            self.tesseract_available = True
            logger.info("Enhanced OCR initialized with Tesseract")
        except ImportError:
            logger.warning("Tesseract not available for enhanced OCR")
    
    def preprocess_image(self, image):
        """Enhanced image preprocessing for better OCR accuracy"""
        try:
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if too small (improve OCR accuracy)
            width, height = image.size
            if width < 1000 or height < 1000:
                scale = max(1000 / width, 1000 / height)
                new_size = (int(width * scale), int(height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            
            # Convert to grayscale
            image = image.convert('L')
            
            # Apply threshold to get black and white
            threshold = 128
            image = image.point(lambda p: 255 if p > threshold else 0)
            
            return image
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            return image
    
    def extract_text_with_preprocessing(self, image_content):
        """Extract text with multiple preprocessing attempts"""
        if not self.tesseract_available:
            return None
        
        try:
            # Load image
            image = Image.open(io.BytesIO(image_content))
            
            # Try multiple OCR configurations
            configs = [
                '--psm 6 --oem 3',  # Assume uniform block of text
                '--psm 11 --oem 3',  # Sparse text
                '--psm 12 --oem 3',  # Sparse text with OSD
                '--psm 3 --oem 3',   # Fully automatic
            ]
            
            all_text = []
            
            # Try with original image
            for config in configs:
                try:
                    text = self.pytesseract.image_to_string(image, config=config)
                    if text and len(text.strip()) > 10:
                        all_text.append(text)
                except Exception:
                    continue
            
            # Try with preprocessed image
            preprocessed = self.preprocess_image(image.copy())
            for config in configs:
                try:
                    text = self.pytesseract.image_to_string(preprocessed, config=config)
                    if text and len(text.strip()) > 10:
                        all_text.append(text)
                except Exception:
                    continue
            
            # Combine all extracted text
            combined_text = '\n'.join(all_text)
            
            if combined_text:
                logger.info(f"Enhanced OCR extracted {len(combined_text)} characters")
                return combined_text
            
            return None
            
        except Exception as e:
            logger.error(f"Enhanced OCR extraction failed: {e}")
            return None
    
    def extract_batch_number(self, text):
        """Extract batch number with multiple patterns"""
        if not text:
            return None
        
        text_upper = text.upper()
        
        # Patterns for batch number
        patterns = [
            r'B\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9]+)',
            r'BATCH\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9]+)',
            r'BATCH\s*[:\-]?\s*([A-Z0-9]+)',
            r'B\.NO\.?\s*[:\-]?\s*([A-Z0-9]+)',
            r'LOT\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9]+)',
            r'LOT\s*[:\-]?\s*([A-Z0-9]+)',
            # Look for patterns like "B.No. E40001"
            r'B\.\s*NO\.\s*([A-Z][0-9]+)',
            # Look for standalone alphanumeric codes (4-10 chars)
            r'\b([A-Z]{1,3}[0-9]{4,8})\b',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                batch = matches[0].strip()
                # Validate batch number (should have letters and numbers)
                if re.search(r'[A-Z]', batch) and re.search(r'[0-9]', batch):
                    if len(batch) >= 4:
                        logger.info(f"Extracted batch number: {batch}")
                        return batch
        
        return None
    
    def extract_manufacture_date(self, text):
        """Extract manufacturing date with multiple patterns"""
        if not text:
            return None
        
        text_upper = text.upper()
        
        # Patterns for manufacturing date
        patterns = [
            r'MFG\.?\s*DT\.?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MFG\.?\s*DATE\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MFG\.?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MANUFACTURED\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MFD\.?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            # Look for patterns like "JAN.24" or "JAN 24"
            r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\.?\s*[0-9]{2,4}',
            # Look for MM/YYYY or MM-YYYY
            r'([0-9]{1,2}[\/\-][0-9]{4})',
            # Look for YYYY-MM or YYYY/MM
            r'([0-9]{4}[\/\-][0-9]{1,2})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                date_str = matches[0].strip()
                parsed_date = self.parse_date(date_str)
                if parsed_date:
                    logger.info(f"Extracted manufacture date: {date_str} -> {parsed_date}")
                    return parsed_date
        
        return None
    
    def extract_expiry_date(self, text):
        """Extract expiry date with multiple patterns"""
        if not text:
            return None
        
        text_upper = text.upper()
        
        # Patterns for expiry date
        patterns = [
            r'EXP\.?\s*DT\.?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'EXP\.?\s*DATE\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'EXP\.?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'EXPIRY\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'EXPIRES?\s*[:\-]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            # Look for patterns like "DEC.26" or "DEC 26"
            r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\.?\s*[0-9]{2,4}',
            # Look for MM/YYYY or MM-YYYY
            r'([0-9]{1,2}[\/\-][0-9]{4})',
            # Look for YYYY-MM or YYYY/MM
            r'([0-9]{4}[\/\-][0-9]{1,2})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                # Get the last match (expiry usually comes after mfg)
                date_str = matches[-1].strip()
                parsed_date = self.parse_date(date_str)
                if parsed_date:
                    logger.info(f"Extracted expiry date: {date_str} -> {parsed_date}")
                    return parsed_date
        
        return None
    
    def parse_date(self, date_str):
        """Parse date string to datetime object"""
        try:
            date_str = date_str.strip().upper()
            
            # Month abbreviations
            months = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            # Try "JAN.24" or "JAN 24" format
            for month_name, month_num in months.items():
                if month_name in date_str:
                    # Extract year
                    year_match = re.search(r'[0-9]{2,4}', date_str)
                    if year_match:
                        year = int(year_match.group())
                        # Convert 2-digit year to 4-digit
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        
                        return datetime(year, month_num, 1).date()
            
            # Try MM/YYYY format
            if '/' in date_str or '-' in date_str:
                parts = re.split(r'[\/\-]', date_str)
                if len(parts) == 2:
                    if len(parts[0]) == 4:  # YYYY/MM
                        year, month = int(parts[0]), int(parts[1])
                    else:  # MM/YYYY
                        month, year = int(parts[0]), int(parts[1])
                    
                    return datetime(year, month, 1).date()
            
        except Exception as e:
            logger.error(f"Date parsing failed for '{date_str}': {e}")
        
        return None
    
    def extract_mrp(self, text):
        """Extract MRP (Maximum Retail Price)"""
        if not text:
            return None
        
        text_upper = text.upper()
        
        # Patterns for MRP
        patterns = [
            r'M\.?R\.?P\.?\s*RS\.?\s*([0-9]+\.?[0-9]*)',
            r'M\.?R\.?P\.?\s*₹\s*([0-9]+\.?[0-9]*)',
            r'M\.?R\.?P\.?\s*[:\-]?\s*([0-9]+\.?[0-9]*)',
            r'MRP\s*RS\.?\s*([0-9]+\.?[0-9]*)',
            r'PRICE\s*RS\.?\s*([0-9]+\.?[0-9]*)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                try:
                    price = float(matches[0])
                    logger.info(f"Extracted MRP: Rs. {price}")
                    return price
                except ValueError:
                    continue
        
        return None
    
    def extract_all_info(self, image_content):
        """Extract all medicine information from image"""
        logger.info("Starting enhanced medicine information extraction...")
        
        # Extract text
        text = self.extract_text_with_preprocessing(image_content)
        
        if not text:
            logger.warning("No text extracted from image")
            return None
        
        logger.info(f"Extracted text preview: {text[:500]}")
        
        # Extract all fields
        result = {
            'batch_number': self.extract_batch_number(text),
            'manufacture_date': self.extract_manufacture_date(text),
            'expiry_date': self.extract_expiry_date(text),
            'mrp': self.extract_mrp(text),
            'raw_text': text
        }
        
        logger.info(f"Extraction results: {result}")
        
        return result


# Global instance
_enhanced_ocr = None

def get_enhanced_ocr():
    """Get or create enhanced OCR instance"""
    global _enhanced_ocr
    if _enhanced_ocr is None:
        _enhanced_ocr = EnhancedMedicineOCR()
    return _enhanced_ocr
