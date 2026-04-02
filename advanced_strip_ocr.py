"""
Advanced Medicine Strip OCR Module
Specialized for handling challenging medicine strip images with:
- Reflective/metallic surfaces
- Multiple orientations
- Embossed text
- Curved surfaces
- Mixed fonts and sizes
"""

import logging
import re
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import OpenCV (optional)
CV2_AVAILABLE = False
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
    logger.info("OpenCV available - using advanced preprocessing")
except ImportError:
    logger.warning("OpenCV not available - using PIL-only preprocessing")

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


class AdvancedStripOCR:
    """Advanced OCR for challenging medicine strip images"""
    
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
    
    def preprocess_for_reflective_surface(self, image):
        """Preprocess image to handle reflective/metallic surfaces (IMPROVED)"""
        try:
            if not CV2_AVAILABLE:
                # PIL-only fallback
                gray = image.convert('L')
                # Enhance contrast heavily
                enhancer = ImageEnhance.Contrast(gray)
                enhanced = enhancer.enhance(3.0)
                # Auto-contrast
                enhanced = ImageOps.autocontrast(enhanced, cutoff=5)
                # Threshold
                enhanced = enhanced.point(lambda x: 0 if x < 128 else 255, '1')
                return enhanced.convert('RGB')
            
            # Convert PIL to OpenCV format
            import numpy as np
            import cv2
            img_array = np.array(image)
            if len(img_array.shape) == 2:
                gray = img_array
            else:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            # Increased clipLimit for better contrast on reflective surfaces
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # Reduce glare using morphological operations
            kernel = np.ones((3,3), np.uint8)
            morph = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)
            
            # Apply bilateral filter to reduce noise while keeping edges
            # Increased parameters for better noise reduction
            filtered = cv2.bilateralFilter(morph, 11, 100, 100)
            
            # Try multiple thresholding methods and combine
            # Method 1: Adaptive Gaussian
            binary1 = cv2.adaptiveThreshold(
                filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            # Method 2: Adaptive Mean
            binary2 = cv2.adaptiveThreshold(
                filtered, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
                cv2.THRESH_BINARY, 15, 3
            )
            
            # Method 3: Otsu's thresholding
            _, binary3 = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Combine results (take the best of all methods)
            combined = cv2.bitwise_or(binary1, cv2.bitwise_or(binary2, binary3))
            
            # Remove small noise
            kernel_small = np.ones((2,2), np.uint8)
            cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_small)
            
            return Image.fromarray(cleaned)
        except Exception as e:
            logger.error(f"Reflective surface preprocessing failed: {e}")
            return image
    
    def preprocess_for_embossed_text(self, image):
        """Preprocess for embossed/raised text (IMPROVED)"""
        try:
            if not CV2_AVAILABLE:
                # PIL-only fallback - use edge enhancement
                gray = image.convert('L')
                # Find edges
                edges = gray.filter(ImageFilter.FIND_EDGES)
                # Enhance edges
                enhancer = ImageEnhance.Contrast(edges)
                edges = enhancer.enhance(2.0)
                # Combine with original
                from PIL import ImageChops
                combined = ImageChops.add(gray, edges, scale=1.5)
                # Sharpen
                combined = combined.filter(ImageFilter.SHARPEN)
                return combined.convert('RGB')
            
            import numpy as np
            import cv2
            img_array = np.array(image)
            if len(img_array.shape) == 2:
                gray = img_array
            else:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # Edge detection to highlight embossed text (multiple methods)
            # Canny edge detection
            edges1 = cv2.Canny(blurred, 30, 100)
            
            # Sobel edge detection (better for embossed text)
            sobelx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
            sobel = np.sqrt(sobelx**2 + sobely**2)
            sobel = np.uint8(sobel / sobel.max() * 255)
            
            # Combine edge detection methods
            edges_combined = cv2.bitwise_or(edges1, sobel)
            
            # Dilate edges to make text more visible
            kernel = np.ones((2,2), np.uint8)
            dilated = cv2.dilate(edges_combined, kernel, iterations=1)
            
            # Combine with original (increased weight on edges)
            combined = cv2.addWeighted(gray, 0.6, dilated, 0.4, 0)
            
            # Apply CLAHE for better contrast
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            enhanced = clahe.apply(combined.astype(np.uint8))
            
            # Apply sharpening kernel
            kernel_sharpen = np.array([[-1,-1,-1],
                                       [-1, 9,-1],
                                       [-1,-1,-1]])
            sharpened = cv2.filter2D(enhanced, -1, kernel_sharpen)
            
            return Image.fromarray(sharpened)
        except Exception as e:
            logger.error(f"Embossed text preprocessing failed: {e}")
            return image
    
    def preprocess_for_stamped_text(self, image):
        """Preprocess for blue/purple stamped text (NEW for strips like Olanzac, Bifilac)"""
        try:
            if not CV2_AVAILABLE:
                # PIL-only fallback - extract blue channel
                if image.mode != 'RGB':
                    return image
                
                # Split channels
                r, g, b = image.split()
                
                # Invert blue channel (stamped text is blue/purple)
                b_inverted = ImageOps.invert(b)
                
                # Enhance contrast
                enhancer = ImageEnhance.Contrast(b_inverted)
                enhanced = enhancer.enhance(3.0)
                
                # Auto-contrast
                enhanced = ImageOps.autocontrast(enhanced, cutoff=10)
                
                # Threshold
                enhanced = enhanced.point(lambda x: 0 if x < 100 else 255, '1')
                
                return enhanced.convert('RGB')
            
            import numpy as np
            import cv2
            img_array = np.array(image)
            if len(img_array.shape) == 2:
                # Already grayscale
                return image
            
            # Extract blue channel (stamped text is often blue/purple)
            blue_channel = img_array[:, :, 2]
            
            # Invert to make blue text dark
            inverted = 255 - blue_channel
            
            # Apply CLAHE for better contrast
            clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8,8))
            enhanced = clahe.apply(inverted)
            
            # Threshold to isolate text
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Remove small noise
            kernel = np.ones((2,2), np.uint8)
            cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
            
            return Image.fromarray(cleaned)
        except Exception as e:
            logger.error(f"Stamped text preprocessing failed: {e}")
            return image
    
    def deskew_image(self, image):
        """Correct image rotation/skew"""
        try:
            if not CV2_AVAILABLE:
                # PIL-only fallback - just return original
                # (deskewing requires OpenCV for accurate angle detection)
                return image
            
            import numpy as np
            import cv2
            img_array = np.array(image)
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Detect edges
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Detect lines using Hough transform
            lines = cv2.HoughLines(edges, 1, np.pi/180, 100)
            
            if lines is not None and len(lines) > 0:
                # Calculate average angle
                angles = []
                for rho, theta in lines[:10, 0]:
                    angle = np.degrees(theta) - 90
                    angles.append(angle)
                
                median_angle = np.median(angles)
                
                # Rotate image if angle is significant
                if abs(median_angle) > 0.5:
                    logger.info(f"Deskewing image by {median_angle:.2f} degrees")
                    return image.rotate(median_angle, expand=True, fillcolor='white')
            
            return image
        except Exception as e:
            logger.error(f"Deskewing failed: {e}")
            return image
    
    def enhance_contrast_and_sharpness(self, image):
        """Enhance image contrast and sharpness"""
        try:
            # Increase contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.5)
            
            # Increase sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            
            # Increase brightness slightly
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.2)
            
            return image
        except Exception as e:
            logger.error(f"Enhancement failed: {e}")
            return image
    
    def upscale_image(self, image, target_size=2000):
        """Upscale small images for better OCR"""
        try:
            width, height = image.size
            if width < target_size or height < target_size:
                scale = max(target_size / width, target_size / height)
                new_size = (int(width * scale), int(height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Upscaled image to {new_size}")
            return image
        except Exception as e:
            logger.error(f"Upscaling failed: {e}")
            return image
    
    def extract_text_multiple_methods(self, image_content):
        """Extract text using multiple preprocessing methods"""
        all_text = []
        
        try:
            # Load original image
            original = Image.open(io.BytesIO(image_content))
            
            # Convert to RGB if needed
            if original.mode != 'RGB':
                original = original.convert('RGB')
            
            logger.info(f"Original image size: {original.size}")
            
            # Method 1: Original image with basic enhancement
            try:
                enhanced = self.enhance_contrast_and_sharpness(original.copy())
                upscaled = self.upscale_image(enhanced)
                text1 = self._ocr_image(upscaled, "Method 1: Enhanced")
                if text1:
                    all_text.append(text1)
            except Exception as e:
                logger.error(f"Method 1 failed: {e}")
            
            # Method 2: Handle reflective surface (IMPROVED for medicine strips)
            try:
                reflective = self.preprocess_for_reflective_surface(original.copy())
                reflective_upscaled = self.upscale_image(reflective)
                text2 = self._ocr_image(reflective_upscaled, "Method 2: Reflective")
                if text2:
                    all_text.append(text2)
            except Exception as e:
                logger.error(f"Method 2 failed: {e}")
            
            # Method 3: Handle embossed text (IMPROVED)
            try:
                embossed = self.preprocess_for_embossed_text(original.copy())
                embossed_upscaled = self.upscale_image(embossed)
                text3 = self._ocr_image(embossed_upscaled, "Method 3: Embossed")
                if text3:
                    all_text.append(text3)
            except Exception as e:
                logger.error(f"Method 3 failed: {e}")
            
            # Method 4: Deskew and enhance
            try:
                deskewed = self.deskew_image(original.copy())
                deskewed_enhanced = self.enhance_contrast_and_sharpness(deskewed)
                deskewed_upscaled = self.upscale_image(deskewed_enhanced)
                text4 = self._ocr_image(deskewed_upscaled, "Method 4: Deskewed")
                if text4:
                    all_text.append(text4)
            except Exception as e:
                logger.error(f"Method 4 failed: {e}")
            
            # Method 5: Grayscale with high contrast
            try:
                gray = original.convert('L')
                gray_enhanced = ImageOps.autocontrast(gray, cutoff=2)
                gray_upscaled = self.upscale_image(gray_enhanced)
                text5 = self._ocr_image(gray_upscaled, "Method 5: Grayscale")
                if text5:
                    all_text.append(text5)
            except Exception as e:
                logger.error(f"Method 5 failed: {e}")
            
            # Method 6: Inverted colors (for dark text on light background)
            try:
                inverted = ImageOps.invert(original.convert('L'))
                inverted_enhanced = self.enhance_contrast_and_sharpness(inverted.convert('RGB'))
                text6 = self._ocr_image(inverted_enhanced, "Method 6: Inverted")
                if text6:
                    all_text.append(text6)
            except Exception as e:
                logger.error(f"Method 6 failed: {e}")
            
            # Method 7: Stamped text (NEW - for blue/purple stamps)
            try:
                stamped = self.preprocess_for_stamped_text(original.copy())
                stamped_upscaled = self.upscale_image(stamped)
                text7 = self._ocr_image(stamped_upscaled, "Method 7: Stamped")
                if text7:
                    all_text.append(text7)
            except Exception as e:
                logger.error(f"Method 7 failed: {e}")
            
            # Combine all extracted text
            combined = '\n'.join(all_text)
            logger.info(f"Total text extracted: {len(combined)} characters from {len(all_text)} methods")
            
            return combined if combined.strip() else None
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}", exc_info=True)
            return None
    
    def _ocr_image(self, image, method_name=""):
        """Perform OCR on preprocessed image"""
        text_results = []
        
        # Try EasyOCR first (better for medicine strips)
        if EASYOCR_AVAILABLE:
            try:
                if self.initialize_easyocr():
                    img_array = np.array(image)
                    results = self.easyocr_reader.readtext(img_array, detail=1)
                    
                    for (bbox, text, confidence) in results:
                        if confidence > 0.2:  # Lower threshold for challenging images
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
        """Extract structured medicine information from text (ENHANCED for real strips)"""
        if not text:
            return {}
        
        text_upper = text.upper()
        info = {}
        
        # Extract medicine name (ENHANCED patterns for real strips like Olanzac, Bifilac)
        name_patterns = [
            # Specific patterns for common medicine names
            r'\b(OLANZAC|OMIZOLE|BIFILAC|BILAC|PARACETAMOL|DOLO|CROCIN|COMBIFLAM)\b',
            # Common medicine suffixes
            r'\b([A-Z][a-z]+(?:zole|zac|lac|flac|pril|olol|pine|mycin|cillin|floxacin|mab|nib|tinib))\b',
            # Medicine with formulation
            r'\b([A-Z][A-Z]+(?:-[A-Z]+)?)\s+(?:SODIUM|EC|SR|DSR|XR|MR|CR)\b',
            # Capitalized words at the beginning (likely medicine name)
            r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\b',
            # All caps medicine names (3-10 letters)
            r'\b([A-Z]{3,10})\b',
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            if matches:
                # Filter out common non-medicine words
                excluded = ['MFG', 'EXP', 'BATCH', 'MRP', 'STRIP', 'TABLETS', 'CAPSULES', 'SYRUP']
                for match in matches:
                    if match not in excluded and len(match) >= 3:
                        info['medicine_name'] = match
                        break
                if 'medicine_name' in info:
                    break
        
        # Extract batch number (ENHANCED for E40001, ALA306 formats)
        batch_patterns = [
            r'B\.?\s*NO\.?\s*[:\-\.]?\s*([A-Z0-9]{4,})',
            r'BATCH\.?\s*NO\.?\s*[:\-\.]?\s*([A-Z0-9]{4,})',
            r'LOT\.?\s*NO\.?\s*[:\-\.]?\s*([A-Z0-9]{4,})',
            # E40001 format (letter + numbers)
            r'\b([A-Z][0-9]{4,6})\b',
            # ALA306 format (letters + numbers)
            r'\b([A-Z]{2,4}[0-9]{2,4})\b',
            # Generic alphanumeric
            r'\b([A-Z]{2,3}[0-9]{4,})\b',
            r'\b([0-9]{2}[A-Z]{2,3}[0-9]{2,})\b',
        ]
        
        for pattern in batch_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                for match in matches:
                    # Validate: must have both letters and numbers, length >= 4
                    if re.search(r'[A-Z]', match) and re.search(r'[0-9]', match) and len(match) >= 4:
                        # Exclude if it looks like a date
                        if not re.match(r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', match):
                            info['batch_number'] = match
                            break
                if 'batch_number' in info:
                    break
        
        # Extract MFG date (ENHANCED for JAN.24, 10/2023 formats)
        mfg_patterns = [
            # MFG. DT. JAN.24 format
            r'MFG\.?\s*DT\.?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MFG\.?\s*[:\-\.]?\s*([0-9]{1,2}[\/\-][0-9]{2,4})',
            r'MFG\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            # MFD. 10/2023 format
            r'MFD\.?\s*[:\-\.]?\s*([0-9]{1,2}[\/\-][0-9]{2,4})',
            r'MFD\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'MANUFACTURED\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
        ]
        
        for pattern in mfg_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                info['manufacture_date'] = self._parse_date(matches[0])
                break
        
        # Extract EXP date (ENHANCED for DEC.26, 09/2025 formats)
        exp_patterns = [
            # EXP. DT. DEC.26 format
            r'EXP\.?\s*DT\.?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'EXP\.?\s*[:\-\.]?\s*([0-9]{1,2}[\/\-][0-9]{2,4})',
            r'EXP\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            # EXPIRY 09/2025 format
            r'EXPIRY\.?\s*[:\-\.]?\s*([0-9]{1,2}[\/\-][0-9]{2,4})',
            r'EXPIRY\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'USE\s+BEFORE\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
            r'BEST\s+BEFORE\.?\s*[:\-\.]?\s*([A-Z]{3}\.?\s*[0-9]{2,4})',
        ]
        
        for pattern in exp_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                info['expiry_date'] = self._parse_date(matches[0])
                break
        
        # Extract MRP (ENHANCED for Rs. 189.00, Rs.140.00 formats)
        mrp_patterns = [
            # M.R.P. Rs. 189.00 format
            r'M\.?R\.?P\.?\s*RS\.?\s*([0-9]+\.?[0-9]*)',
            r'M\.?R\.?P\.?\s*[:\-\.]?\s*₹?\s*([0-9]+\.?[0-9]*)',
            # M.R.P.Rs.140.00 format (no space)
            r'M\.?R\.?P\.?RS\.?\s*([0-9]+\.?[0-9]*)',
            r'MRP\.?\s*[:\-\.]?\s*([0-9]+\.?[0-9]*)',
            r'RS\.?\s*([0-9]+\.?[0-9]*)',
            r'₹\s*([0-9]+\.?[0-9]*)',
        ]
        
        for pattern in mrp_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                try:
                    mrp_val = float(matches[0].replace(',', ''))
                    # Validate reasonable price range (10-999 Rs)
                    if 10 <= mrp_val <= 999:
                        info['mrp'] = mrp_val
                        break
                except ValueError:
                    continue
        
        # Extract composition
        comp_patterns = [
            r'COMPOSITION[:\-]?\s*(.+?)(?:MFG|BATCH|EXPIRY|MRP|$)',
            r'EACH.*?CONTAINS[:\-]?\s*(.+?)(?:MFG|BATCH|EXPIRY|MRP|$)',
            r'CONTENTS?[:\-]?\s*(.+?)(?:MFG|BATCH|EXPIRY|MRP|$)',
        ]
        
        for pattern in comp_patterns:
            matches = re.findall(pattern, text_upper, re.DOTALL)
            if matches:
                comp = matches[0].strip()[:200]  # Limit length
                if len(comp) > 5:  # Ensure it's not just noise
                    info['composition'] = comp
                    break
        
        logger.info(f"Extracted info: {info}")
        return info
    
    def _parse_date(self, date_str):
        """Parse date string to standard format (ENHANCED for JAN.24, 10/2023 formats)"""
        try:
            date_str = date_str.strip().upper()
            
            # Month mapping
            months = {
                'JAN': 1, 'JANUARY': 1,
                'FEB': 2, 'FEBRUARY': 2,
                'MAR': 3, 'MARCH': 3,
                'APR': 4, 'APRIL': 4,
                'MAY': 5,
                'JUN': 6, 'JUNE': 6,
                'JUL': 7, 'JULY': 7,
                'AUG': 8, 'AUGUST': 8,
                'SEP': 9, 'SEPT': 9, 'SEPTEMBER': 9,
                'OCT': 10, 'OCTOBER': 10,
                'NOV': 11, 'NOVEMBER': 11,
                'DEC': 12, 'DECEMBER': 12
            }
            
            # Try MM/YYYY or MM-YYYY or MM.YYYY (10/2023, 09/2025)
            if '/' in date_str or '-' in date_str or '.' in date_str:
                parts = re.split(r'[\/\-\.]', date_str)
                if len(parts) >= 2:
                    try:
                        # Try month/year first
                        month = int(parts[0])
                        year = int(parts[1])
                        # Handle 2-digit years
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if 1 <= month <= 12 and 2000 <= year <= 2050:
                            return datetime(year, month, 1).strftime('%m/%Y')
                    except ValueError:
                        pass
            
            # Try MON.YYYY or MON YYYY or MONYYYY (JAN.24, DEC.26)
            for month_name, month_num in months.items():
                if month_name in date_str:
                    # Extract year (handle both 2 and 4 digit years)
                    year_match = re.search(r'[0-9]{2,4}', date_str)
                    if year_match:
                        year = int(year_match.group())
                        # Handle 2-digit years (24 -> 2024, 26 -> 2026)
                        if year < 100:
                            # Assume 20-50 is 2020-2050, 51-99 is 1951-1999
                            year = 2000 + year if year < 50 else 1900 + year
                        if 2000 <= year <= 2050:
                            return datetime(year, month_num, 1).strftime('%m/%Y')
            
            # Try YYYY-MM or YYYY/MM
            year_month_match = re.match(r'([0-9]{4})[\/\-\.]([0-9]{1,2})', date_str)
            if year_month_match:
                year = int(year_month_match.group(1))
                month = int(year_month_match.group(2))
                if 1 <= month <= 12 and 2000 <= year <= 2050:
                    return datetime(year, month, 1).strftime('%m/%Y')
            
            return date_str
        except Exception as e:
            logger.error(f"Date parsing failed for '{date_str}': {e}")
            return date_str
    
    def process_medicine_strip(self, image_content):
        """Main method to process medicine strip image"""
        logger.info("Starting advanced medicine strip OCR...")
        
        # Extract text using multiple methods
        text = self.extract_text_multiple_methods(image_content)
        
        if not text:
            logger.warning("No text extracted from image")
            return None
        
        # Extract structured information
        info = self.extract_medicine_info(text)
        info['raw_text'] = text
        
        return info


# Global instance
_advanced_ocr = None

def get_advanced_ocr():
    """Get or create advanced OCR instance"""
    global _advanced_ocr
    if _advanced_ocr is None:
        _advanced_ocr = AdvancedStripOCR()
    return _advanced_ocr


def process_medicine_strip_image(image_content):
    """Process medicine strip image and extract information"""
    ocr = get_advanced_ocr()
    return ocr.process_medicine_strip(image_content)
