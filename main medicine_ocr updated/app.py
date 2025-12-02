from flask import Flask, request, render_template, jsonify, redirect, url_for, session, flash
from google.cloud import vision
import re, os
import sys
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import io
from google.cloud.vision_v1 import types
import logging
import base64
import json

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Set up logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log API key status
if os.environ.get('GEMINI_API_KEY'):
    logger.info("✓ Gemini API key loaded from environment")
else:
    logger.warning("⚠ No Gemini API key found - will use FREE OCR only")

# Add current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import free OCR module
try:
    from free_ocr import extract_medicines_from_prescription_free, EASYOCR_AVAILABLE, PADDLEOCR_AVAILABLE, TESSERACT_AVAILABLE
    FREE_OCR_AVAILABLE = EASYOCR_AVAILABLE or PADDLEOCR_AVAILABLE or TESSERACT_AVAILABLE
    logger.info(f"Free OCR module loaded - EasyOCR: {EASYOCR_AVAILABLE}, PaddleOCR: {PADDLEOCR_AVAILABLE}, Tesseract: {TESSERACT_AVAILABLE}")
except ImportError as e:
    FREE_OCR_AVAILABLE = False
    logger.warning(f"Free OCR module not available: {e}")

# Import advanced strip OCR module (Lite version - no OpenCV required)
try:
    from advanced_strip_ocr_lite import get_advanced_ocr, process_medicine_strip_image
    ADVANCED_OCR_AVAILABLE = True
    logger.info("Advanced Strip OCR (Lite) module loaded successfully")
except ImportError as e:
    ADVANCED_OCR_AVAILABLE = False
    logger.warning(f"Advanced Strip OCR module not available: {e}")

# API Key Configuration
# Set as environment variable: export GEMINI_API_KEY="your-key"
# Or use FREE OCR (Tesseract) - no API key needed!

# Try to import AI libraries
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not available. Install with: pip install google-generativeai")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai not available. Install with: pip install openai")

# ─── App & DB Setup ───────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medicine.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'supersecretkey'  # Needed for session management

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# Initialize Google Vision client with error handling
global_vision_client = None
try:
    env_cred = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if env_cred and os.path.exists(env_cred):
        logger.info(f"Using GOOGLE_APPLICATION_CREDENTIALS from environment: {env_cred}")
    else:
        local_cred = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vision-key.json')
        if os.path.exists(local_cred):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = local_cred
            logger.info(f"Using local vision key at: {local_cred}")
        else:
            logger.warning("No Google credentials found; OCR features will be disabled.")
            raise FileNotFoundError("No credentials available")
    global_vision_client = vision.ImageAnnotatorClient()
    logger.info("Successfully initialized Google Cloud Vision client")
except Exception as e:
    logger.warning(f"Google Cloud Vision not initialized: {str(e)}")

class Medicine(db.Model):
    batch_id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    manufacture_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)

class MedicineEnquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    enquiry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_name = db.Column(db.String(100), nullable=False)

# Simple order models for user checkout
class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    medicine_batch_id = db.Column(db.Integer, nullable=False)
    medicine_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='success')
    txn_id = db.Column(db.String(100))
    amount = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Initial medicine data
initial_medicine_data = [
    {"batch_id": 1, "medicine_name": "Augmentin", "brand": "GSK", "category": "Tablet", "batch_number": "AUG-GSK-2026", "quantity": 120, "price_per_unit": 32.00, "manufacture_date": "2024-02-15", "expiry_date": "2026-02-15"},
    {"batch_id": 2, "medicine_name": "Avil", "brand": "Sanofi", "category": "Tablet", "batch_number": "AVIL-SAN-2026", "quantity": 90, "price_per_unit": 5.00, "manufacture_date": "2023-12-10", "expiry_date": "2026-12-10"},
    {"batch_id": 3, "medicine_name": "Benadryl", "brand": "J&J", "category": "Syrup", "batch_number": "BENA-JJ-2026", "quantity": 60, "price_per_unit": 75.00, "manufacture_date": "2024-04-20", "expiry_date": "2026-04-20"},
    {"batch_id": 4, "medicine_name": "Brufen", "brand": "Abbott", "category": "Tablet", "batch_number": "BRUF-ABB-2026", "quantity": 85, "price_per_unit": 20.00, "manufacture_date": "2024-03-12", "expiry_date": "2026-03-12"},
    {"batch_id": 5, "medicine_name": "Brufen", "brand": "Abbott", "category": "Tablet", "batch_number": "BRUF-ABB-2028", "quantity": 60, "price_per_unit": 20.00, "manufacture_date": "2025-06-18", "expiry_date": "2028-06-18"},
    {"batch_id": 6, "medicine_name": "Calpol", "brand": "GSK", "category": "Tablet", "batch_number": "CALP-GSK-2026", "quantity": 100, "price_per_unit": 18.00, "manufacture_date": "2024-06-15", "expiry_date": "2026-06-15"},
    {"batch_id": 7, "medicine_name": "Calpol", "brand": "GSK", "category": "Tablet", "batch_number": "CALP-GSK-2027", "quantity": 80, "price_per_unit": 18.00, "manufacture_date": "2025-03-01", "expiry_date": "2027-03-01"},
    {"batch_id": 8, "medicine_name": "Cetrizine", "brand": "Cipla", "category": "Tablet", "batch_number": "CET-CIP-2026", "quantity": 110, "price_per_unit": 3.00, "manufacture_date": "2024-01-22", "expiry_date": "2026-01-22"},
    {"batch_id": 9, "medicine_name": "Combiflam", "brand": "Sanofi", "category": "Tablet", "batch_number": "COMB-SAN-2026", "quantity": 150, "price_per_unit": 10.00, "manufacture_date": "2023-03-22", "expiry_date": "2026-03-22"},
    {"batch_id": 10, "medicine_name": "Combiflam", "brand": "Sanofi", "category": "Tablet", "batch_number": "COMB-SAN-2027", "quantity": 120, "price_per_unit": 10.00, "manufacture_date": "2024-02-10", "expiry_date": "2027-02-10"},
    {"batch_id": 11, "medicine_name": "Dolo 650", "brand": "Micro Labs", "category": "Tablet", "batch_number": "DL650-2038", "quantity": 100, "price_per_unit": 25.00, "manufacture_date": "2023-06-27", "expiry_date": "2038-06-27"},
    {"batch_id": 12, "medicine_name": "Dolo 650", "brand": "Micro Labs", "category": "Tablet", "batch_number": "DL650-2027", "quantity": 75, "price_per_unit": 25.00, "manufacture_date": "2022-07-23", "expiry_date": "2027-07-23"},
    {"batch_id": 13, "medicine_name": "Domstal", "brand": "Torrent", "category": "Tablet", "batch_number": "DOMS-TOR-2027", "quantity": 130, "price_per_unit": 17.00, "manufacture_date": "2024-01-10", "expiry_date": "2027-01-10"},
    {"batch_id": 14, "medicine_name": "Domstal", "brand": "Torrent", "category": "Tablet", "batch_number": "DOMS-TOR-2026", "quantity": 110, "price_per_unit": 17.00, "manufacture_date": "2023-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 15, "medicine_name": "Electral", "brand": "FDC", "category": "Powder", "batch_number": "ELEC-FDC-2025", "quantity": 50, "price_per_unit": 12.00, "manufacture_date": "2023-12-01", "expiry_date": "2025-12-01"},
    {"batch_id": 16, "medicine_name": "Electral", "brand": "FDC", "category": "Powder", "batch_number": "ELEC-FDC-2026", "quantity": 70, "price_per_unit": 12.00, "manufacture_date": "2024-04-14", "expiry_date": "2026-04-14"},
    {"batch_id": 17, "medicine_name": "Eno", "brand": "GSK", "category": "Powder", "batch_number": "ENO-GSK-2025", "quantity": 100, "price_per_unit": 7.00, "manufacture_date": "2023-09-01", "expiry_date": "2025-09-01"},
    {"batch_id": 18, "medicine_name": "Fepanil", "brand": "Sun Pharma", "category": "Tablet", "batch_number": "FEP-SUN-2026", "quantity": 120, "price_per_unit": 9.00, "manufacture_date": "2024-03-15", "expiry_date": "2026-03-15"},
    {"batch_id": 19, "medicine_name": "Flexon", "brand": "Aristo", "category": "Tablet", "batch_number": "FLEX-ARI-2026", "quantity": 100, "price_per_unit": 11.00, "manufacture_date": "2024-02-10", "expiry_date": "2026-02-10"},
    {"batch_id": 20, "medicine_name": "Gaviscon", "brand": "Reckitt", "category": "Suspension", "batch_number": "GAVI-REC-2026", "quantity": 70, "price_per_unit": 30.00, "manufacture_date": "2024-05-05", "expiry_date": "2026-05-05"},
    {"batch_id": 21, "medicine_name": "Gelusil", "brand": "Pfizer", "category": "Suspension", "batch_number": "GELU-PFZ-2026", "quantity": 75, "price_per_unit": 30.00, "manufacture_date": "2023-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 22, "medicine_name": "Gelusil", "brand": "Pfizer", "category": "Suspension", "batch_number": "GELU-PFZ-2027", "quantity": 55, "price_per_unit": 30.00, "manufacture_date": "2024-05-10", "expiry_date": "2027-05-10"},
    {"batch_id": 23, "medicine_name": "Honitus", "brand": "Dabur", "category": "Syrup", "batch_number": "HONI-DAB-2026", "quantity": 80, "price_per_unit": 90.00, "manufacture_date": "2024-02-25", "expiry_date": "2026-02-25"},
    {"batch_id": 24, "medicine_name": "Hifenac", "brand": "Intas", "category": "Tablet", "batch_number": "HIFE-INT-2026", "quantity": 90, "price_per_unit": 18.00, "manufacture_date": "2024-01-30", "expiry_date": "2026-01-30"},
    {"batch_id": 25, "medicine_name": "Ibugesic", "brand": "Cipla", "category": "Tablet", "batch_number": "IBU-CIP-2026", "quantity": 100, "price_per_unit": 10.00, "manufacture_date": "2024-06-10", "expiry_date": "2026-06-10"},
    {"batch_id": 26, "medicine_name": "Iodex", "brand": "GSK", "category": "Ointment", "batch_number": "IOD-GSK-2026", "quantity": 60, "price_per_unit": 40.00, "manufacture_date": "2024-03-12", "expiry_date": "2026-03-12"},
    {"batch_id": 27, "medicine_name": "Jiffy", "brand": "Cadila", "category": "Tablet", "batch_number": "JIFF-CAD-2026", "quantity": 70, "price_per_unit": 8.00, "manufacture_date": "2024-04-06", "expiry_date": "2026-04-06"},
    {"batch_id": 28, "medicine_name": "Junior Lanzol", "brand": "Cipla", "category": "Tablet", "batch_number": "JLAN-CIP-2026", "quantity": 60, "price_per_unit": 14.00, "manufacture_date": "2024-02-12", "expiry_date": "2026-02-12"},
    {"batch_id": 29, "medicine_name": "Ketanov", "brand": "Sun Pharma", "category": "Tablet", "batch_number": "KETA-SUN-2026", "quantity": 85, "price_per_unit": 22.00, "manufacture_date": "2024-01-18", "expiry_date": "2026-01-18"},
    {"batch_id": 30, "medicine_name": "Ketorol", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "KETO-DRD-2026", "quantity": 90, "price_per_unit": 25.00, "manufacture_date": "2024-03-08", "expiry_date": "2026-03-08"},
    {"batch_id": 31, "medicine_name": "Limcee", "brand": "Abbott", "category": "Tablet", "batch_number": "LIM-ABB-2026", "quantity": 100, "price_per_unit": 7.00, "manufacture_date": "2024-02-22", "expiry_date": "2026-02-22"},
    {"batch_id": 32, "medicine_name": "Liv52", "brand": "Himalaya", "category": "Syrup", "batch_number": "LIV52-HIM-2027", "quantity": 60, "price_per_unit": 85.00, "manufacture_date": "2024-02-01", "expiry_date": "2027-02-01"},
    {"batch_id": 33, "medicine_name": "Liv52", "brand": "Himalaya", "category": "Syrup", "batch_number": "LIV52-HIM-2026", "quantity": 50, "price_per_unit": 85.00, "manufacture_date": "2023-01-18", "expiry_date": "2026-01-18"},
    {"batch_id": 34, "medicine_name": "Meftal Spas", "brand": "Blue Cross", "category": "Tablet", "batch_number": "MEF-BC-2026", "quantity": 120, "price_per_unit": 15.00, "manufacture_date": "2024-04-11", "expiry_date": "2026-04-11"},
    {"batch_id": 35, "medicine_name": "Metrogyl", "brand": "JB Chem", "category": "Tablet", "batch_number": "MET-JB-2026", "quantity": 110, "price_per_unit": 12.00, "manufacture_date": "2024-03-05", "expiry_date": "2026-03-20"},
    {"batch_id": 36, "medicine_name": "Nasivion", "brand": "Bayer", "category": "Drops", "batch_number": "NAS-BAY-2026", "quantity": 75, "price_per_unit": 65.00, "manufacture_date": "2024-05-20", "expiry_date": "2026-05-20"},
    {"batch_id": 37, "medicine_name": "Norflox", "brand": "Cipla", "category": "Tablet", "batch_number": "NOR-CIP-2026", "quantity": 90, "price_per_unit": 12.00, "manufacture_date": "2024-02-28", "expiry_date": "2026-02-28"},
    {"batch_id": 38, "medicine_name": "Omez", "brand": "Dr. Reddy's", "category": "Capsule", "batch_number": "OMEZ-DRD-2025", "quantity": 120, "price_per_unit": 12.50, "manufacture_date": "2023-11-15", "expiry_date": "2025-11-15"},
    {"batch_id": 39, "medicine_name": "Omez", "brand": "Dr. Reddy's", "category": "Capsule", "batch_number": "OMEZ-DRD-2026", "quantity": 90, "price_per_unit": 12.50, "manufacture_date": "2024-01-05", "expiry_date": "2026-01-05"},
    {"batch_id": 40, "medicine_name": "Ondem", "brand": "Alkem", "category": "Tablet", "batch_number": "OND-ALK-2026", "quantity": 95, "price_per_unit": 14.00, "manufacture_date": "2023-08-18", "expiry_date": "2026-08-18"},
    {"batch_id": 41, "medicine_name": "Ondem", "brand": "Alkem", "category": "Tablet", "batch_number": "OND-ALK-2027", "quantity": 100, "price_per_unit": 14.00, "manufacture_date": "2024-03-22", "expiry_date": "2027-03-22"},
    {"batch_id": 42, "medicine_name": "Pantoprazole", "brand": "Zydus", "category": "Tablet", "batch_number": "PANTO-ZYD-2026", "quantity": 110, "price_per_unit": 22.00, "manufacture_date": "2023-10-10", "expiry_date": "2026-10-10"},
    {"batch_id": 43, "medicine_name": "Pantoprazole", "brand": "Zydus", "category": "Tablet", "batch_number": "PANTO-ZYD-2027", "quantity": 95, "price_per_unit": 22.00, "manufacture_date": "2024-06-06", "expiry_date": "2027-06-06"},
    {"batch_id": 44, "medicine_name": "Paracetamol", "brand": "Cipla", "category": "Tablet", "batch_number": "PARA-CIPLA-2026", "quantity": 200, "price_per_unit": 15.00, "manufacture_date": "2024-05-12", "expiry_date": "2026-05-12"},
    {"batch_id": 45, "medicine_name": "Paracetamol", "brand": "Cipla", "category": "Tablet", "batch_number": "PARA-CIPLA-2027", "quantity": 160, "price_per_unit": 15.00, "manufacture_date": "2025-01-20", "expiry_date": "2027-01-20"},
    {"batch_id": 46, "medicine_name": "Quadriderm", "brand": "MSD", "category": "Cream", "batch_number": "QUAD-MSD-2026", "quantity": 50, "price_per_unit": 60.00, "manufacture_date": "2024-03-25", "expiry_date": "2026-03-25"},
    {"batch_id": 47, "medicine_name": "Quinidine", "brand": "Sandoz", "category": "Tablet", "batch_number": "QUIN-SAN-2026", "quantity": 40, "price_per_unit": 28.00, "manufacture_date": "2024-04-18", "expiry_date": "2026-04-18"},
    {"batch_id": 48, "medicine_name": "Rantac", "brand": "JB Chem", "category": "Tablet", "batch_number": "RANT-JB-2026", "quantity": 100, "price_per_unit": 9.00, "manufacture_date": "2024-01-07", "expiry_date": "2026-01-07"},
    {"batch_id": 49, "medicine_name": "Revital", "brand": "Sun Pharma", "category": "Capsule", "batch_number": "REVI-SUN-2027", "quantity": 80, "price_per_unit": 120.00, "manufacture_date": "2024-04-01", "expiry_date": "2027-04-01"},
    {"batch_id": 50, "medicine_name": "Revital", "brand": "Sun Pharma", "category": "Capsule", "batch_number": "REVI-SUN-2025", "quantity": 60, "price_per_unit": 120.00, "manufacture_date": "2023-02-01", "expiry_date": "2025-02-01"},
    {"batch_id": 51, "medicine_name": "Sinarest", "brand": "Centaur", "category": "Tablet", "batch_number": "SINA-CEN-2025", "quantity": 90, "price_per_unit": 8.00, "manufacture_date": "2023-09-05", "expiry_date": "2025-09-05"},
    {"batch_id": 52, "medicine_name": "Sinarest", "brand": "Centaur", "category": "Tablet", "batch_number": "SINA-CEN-2026", "quantity": 100, "price_per_unit": 8.00, "manufacture_date": "2024-07-01", "expiry_date": "2026-07-01"},
    {"batch_id": 53, "medicine_name": "Soframycin", "brand": "Sanofi", "category": "Cream", "batch_number": "SOFR-SAN-2026", "quantity": 70, "price_per_unit": 32.00, "manufacture_date": "2023-04-21", "expiry_date": "2026-04-21"},
    {"batch_id": 54, "medicine_name": "Soframycin", "brand": "Sanofi", "category": "Cream", "batch_number": "SOFR-SAN-2027", "quantity": 50, "price_per_unit": 32.00, "manufacture_date": "2024-05-01", "expiry_date": "2027-05-01"},
    {"batch_id": 55, "medicine_name": "Strepsils", "brand": "Reckitt", "category": "Lozenges", "batch_number": "STRE-REC-2025", "quantity": 100, "price_per_unit": 5.00, "manufacture_date": "2023-01-01", "expiry_date": "2025-01-01"},
    {"batch_id": 56, "medicine_name": "Strepsils", "brand": "Reckitt", "category": "Lozenges", "batch_number": "STRE-REC-2027", "quantity": 120, "price_per_unit": 5.00, "manufacture_date": "2024-08-09", "expiry_date": "2027-08-09"},
    {"batch_id": 57, "medicine_name": "Taxim-O", "brand": "Alkem", "category": "Tablet", "batch_number": "TAX-ALK-2026", "quantity": 85, "price_per_unit": 45.00, "manufacture_date": "2024-05-02", "expiry_date": "2026-05-02"},
    {"batch_id": 58, "medicine_name": "Thyronorm", "brand": "Abbott", "category": "Tablet", "batch_number": "THYR-ABB-2027", "quantity": 110, "price_per_unit": 18.00, "manufacture_date": "2024-02-19", "expiry_date": "2027-02-19"},
    {"batch_id": 59, "medicine_name": "Thyronorm", "brand": "Abbott", "category": "Tablet", "batch_number": "THYR-ABB-2026", "quantity": 90, "price_per_unit": 18.00, "manufacture_date": "2023-03-14", "expiry_date": "2026-03-14"},
    {"batch_id": 60, "medicine_name": "Ulgel", "brand": "Zydus", "category": "Suspension", "batch_number": "ULG-ZYD-2026", "quantity": 70, "price_per_unit": 25.00, "manufacture_date": "2024-04-01", "expiry_date": "2026-04-01"},
    {"batch_id": 61, "medicine_name": "Unienzyme", "brand": "Torrent", "category": "Tablet", "batch_number": "UNI-TOR-2026", "quantity": 95, "price_per_unit": 13.00, "manufacture_date": "2024-02-18", "expiry_date": "2026-02-18"},
    {"batch_id": 62, "medicine_name": "Vicks", "brand": "P&G", "category": "Ointment", "batch_number": "VICK-PG-2026", "quantity": 80, "price_per_unit": 56.00, "manufacture_date": "2024-03-14", "expiry_date": "2026-03-14"},
    {"batch_id": 63, "medicine_name": "Volini", "brand": "Sun Pharma", "category": "Gel", "batch_number": "VOLI-SUN-2025", "quantity": 60, "price_per_unit": 65.00, "manufacture_date": "2023-05-10", "expiry_date": "2025-05-10"},
    {"batch_id": 64, "medicine_name": "Volini", "brand": "Sun Pharma", "category": "Gel", "batch_number": "VOLI-SUN-2026", "quantity": 50, "price_per_unit": 65.00, "manufacture_date": "2024-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 65, "medicine_name": "Wikoryl", "brand": "Alembic", "category": "Tablet", "batch_number": "WIK-ALE-2026", "quantity": 100, "price_per_unit": 8.00, "manufacture_date": "2024-02-28", "expiry_date": "2026-02-28"},
    {"batch_id": 66, "medicine_name": "Wysolone", "brand": "Pfizer", "category": "Tablet", "batch_number": "WYS-PFZ-2026", "quantity": 90, "price_per_unit": 20.00, "manufacture_date": "2024-01-25", "expiry_date": "2026-01-25"},
    {"batch_id": 67, "medicine_name": "Xarelto", "brand": "Bayer", "category": "Tablet", "batch_number": "XAR-BAY-2026", "quantity": 60, "price_per_unit": 150.00, "manufacture_date": "2024-01-30", "expiry_date": "2026-01-30"},
    {"batch_id": 68, "medicine_name": "Xone", "brand": "Alkem", "category": "Injection", "batch_number": "XON-ALK-2026", "quantity": 40, "price_per_unit": 90.00, "manufacture_date": "2024-05-12", "expiry_date": "2026-05-12"},
    {"batch_id": 69, "medicine_name": "Yogurt Sachets", "brand": "Abbott", "category": "Powder", "batch_number": "YOG-ABB-2026", "quantity": 70, "price_per_unit": 35.00, "manufacture_date": "2024-02-07", "expiry_date": "2026-02-07"},
    {"batch_id": 70, "medicine_name": "Yondelis", "brand": "Janssen", "category": "Injection", "batch_number": "YON-JAN-2026", "quantity": 30, "price_per_unit": 1200.00, "manufacture_date": "2024-03-20", "expiry_date": "2026-03-20"},
    {"batch_id": 71, "medicine_name": "Zincovit", "brand": "Apex", "category": "Tablet", "batch_number": "ZINC-APX-2026", "quantity": 110, "price_per_unit": 10.00, "manufacture_date": "2024-06-02", "expiry_date": "2026-06-02"},
    {"batch_id": 72, "medicine_name": "Zyrtec", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "ZYRC-DRD-2025", "quantity": 90, "price_per_unit": 22.00, "manufacture_date": "2023-07-09", "expiry_date": "2025-07-09"},
    {"batch_id": 73, "medicine_name": "Zyrtec", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "ZYRC-DRD-2027", "quantity": 75, "price_per_unit": 22.00, "manufacture_date": "2024-04-15", "expiry_date": "2027-04-15"}
]

with app.app_context():
    db.create_all()
    # Check if the database is empty before populating
    if not Medicine.query.first():
        for data in initial_medicine_data:
            data['manufacture_date'] = datetime.strptime(data['manufacture_date'], '%Y-%m-%d').date()
            data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            medicine = Medicine(**data)
            db.session.add(medicine)
        db.session.commit()

# ─── Medicine Database ────────────────────────────────────────────────────────
MEDICINE_DB = {
    'A': ['Augmentin', 'Avil'],
    'B': ['Benadryl', 'Brufen'],
    'C': ['Cetrizine', 'Combiflam'],
    'D': ['Dolo 650', 'Domstal'],
    'E': ['Eno', 'Electral'],
    'F': ['Flexon', 'Fepanil'],
    'G': ['Gelusil', 'Gaviscon'],
    'H': ['Honitus', 'Hifenac'],
    'I': ['Ibugesic', 'Iodex'],
    'J': ['Junior Lanzol', 'Jiffy'],
    'K': ['Ketorol', 'Ketanov'],
    'L': ['Liv52', 'Limcee'],
    'M': ['Meftal Spas', 'Metrogyl'],
    'N': ['Norflox', 'Nasivion'],
    'O': ['Omez', 'Ondem'],
    'P': ['Paracetamol', 'Pantoprazole'],
    'Q': ['Quadriderm', 'Quinidine'],
    'R': ['Rantac', 'Revital'],
    'S': ['Sinarest', 'Soframycin'],
    'T': ['Thyronorm', 'Taxim-O'],
    'U': ['Ulgel', 'Unienzyme'],
    'V': ['Volini', 'Vicks'],
    'W': ['Wikoryl', 'Wysolone'],
    'X': ['Xarelto', 'Xone'],
    'Y': ['Yondelis', 'Yogurt Sachets'],
    'Z': ['Zyrtec', 'Zincovit']
}

# Medicine information database
MEDICINE_INFO = {
    "Augmentin": {
        "uses": "Bacterial infections",
        "side_effects": "Diarrhea, Rash",
        "dosage": "As directed by physician"
    },
    "Avil": {
        "uses": "Allergy, Cold",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "1 tablet twice daily"
    },
    "Benadryl": {
        "uses": "Cough, Allergy",
        "side_effects": "Drowsiness, Dizziness",
        "dosage": "2 tsp thrice daily"
    },
    "Brufen": {
        "uses": "Pain relief, Fever",
        "side_effects": "Nausea, Stomach pain",
        "dosage": "1 tablet every 8 hours"
    },
    "Cetrizine": {
        "uses": "Allergies, Runny nose",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "1 tablet once daily"
    },
    "Combiflam": {
        "uses": "Pain, Fever",
        "side_effects": "Stomach upset, Nausea",
        "dosage": "1 tablet twice daily"
    },
    "Dolo 650": {
        "uses": "Fever, Headache",
        "side_effects": "Liver damage (overdose)",
        "dosage": "1 tablet every 6 hours"
    },
    "Domstal": {
        "uses": "Nausea, Vomiting",
        "side_effects": "Dry mouth, Drowsiness",
        "dosage": "1 tablet before meals"
    },
    "Eno": {
        "uses": "Acidity, Indigestion",
        "side_effects": "None common",
        "dosage": "1 tsp in water as needed"
    },
    "Electral": {
        "uses": "Dehydration, Electrolyte imbalance",
        "side_effects": "None common",
        "dosage": "Dissolve 1 packet in 1L water"
    },
    "Flexon": {
        "uses": "Pain relief, Fever",
        "side_effects": "Nausea, Stomach pain",
        "dosage": "1 tablet twice daily"
    },
    "Fepanil": {
        "uses": "Fever, Cold",
        "side_effects": "Liver effects (overdose)",
        "dosage": "1 tablet every 6 hours"
    },
    "Gelusil": {
        "uses": "Acidity, Gas",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Gaviscon": {
        "uses": "Heartburn, Indigestion",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Honitus": {
        "uses": "Cough, Cold",
        "side_effects": "Drowsiness (rare)",
        "dosage": "2 tsp thrice daily"
    },
    "Hifenac": {
        "uses": "Pain, Inflammation",
        "side_effects": "Acidity, Nausea",
        "dosage": "1 tablet after food"
    },
    "Ibugesic": {
        "uses": "Fever, Pain",
        "side_effects": "Stomach pain, Nausea",
        "dosage": "1 tablet every 6–8 hours"
    },
    "Iodex": {
        "uses": "Muscle pain",
        "side_effects": "Skin irritation",
        "dosage": "Apply externally on affected area"
    },
    "Junior Lanzol": {
        "uses": "Acidity in kids",
        "side_effects": "Abdominal pain, Diarrhea",
        "dosage": "As prescribed by pediatrician"
    },
    "Jiffy": {
        "uses": "Fever, Cold",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "As prescribed"
    },
    "Ketorol": {
        "uses": "Severe pain",
        "side_effects": "Stomach pain, Drowsiness",
        "dosage": "As prescribed"
    },
    "Ketanov": {
        "uses": "Post-operative pain",
        "side_effects": "Nausea, Dizziness",
        "dosage": "As directed"
    },
    "Liv52": {
        "uses": "Liver health",
        "side_effects": "None significant",
        "dosage": "2 tablets daily"
    },
    "Limcee": {
        "uses": "Vitamin C supplement",
        "side_effects": "None common",
        "dosage": "1 tablet daily"
    },
    "Meftal Spas": {
        "uses": "Menstrual pain, Spasms",
        "side_effects": "Dizziness, Nausea",
        "dosage": "1 tablet as needed"
    },
    "Metrogyl": {
        "uses": "Bacterial infections",
        "side_effects": "Metallic taste, Nausea",
        "dosage": "1 tablet twice daily"
    },
    "Norflox": {
        "uses": "UTI, Diarrhea",
        "side_effects": "Nausea, Headache",
        "dosage": "1 tablet twice daily"
    },
    "Nasivion": {
        "uses": "Nasal congestion",
        "side_effects": "Burning sensation",
        "dosage": "2 drops per nostril"
    },
    "Omez": {
        "uses": "Acidity, Ulcer",
        "side_effects": "Headache, Nausea",
        "dosage": "1 capsule before food"
    },
    "Ondem": {
        "uses": "Nausea, Vomiting",
        "side_effects": "Headache, Constipation",
        "dosage": "As directed by physician"
    },
    "Paracetamol": {
        "uses": "Fever, Mild pain",
        "side_effects": "Liver toxicity (overuse)",
        "dosage": "1 tablet every 6 hours"
    },
    "Pantoprazole": {
        "uses": "GERD, Acidity",
        "side_effects": "Abdominal pain",
        "dosage": "1 tablet before breakfast"
    },
    "Quadriderm": {
        "uses": "Skin infections",
        "side_effects": "Skin irritation",
        "dosage": "Apply thin layer twice daily"
    },
    "Quinidine": {
        "uses": "Irregular heartbeat",
        "side_effects": "Dizziness, Nausea",
        "dosage": "As directed"
    },
    "Rantac": {
        "uses": "Acidity, Ulcers",
        "side_effects": "Constipation",
        "dosage": "1 tablet before meals"
    },
    "Revital": {
        "uses": "Energy supplement",
        "side_effects": "None significant",
        "dosage": "1 capsule daily"
    },
    "Sinarest": {
        "uses": "Cold, Allergy",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet twice daily"
    },
    "Soframycin": {
        "uses": "Wound healing",
        "side_effects": "Skin irritation",
        "dosage": "Apply externally"
    },
    "Thyronorm": {
        "uses": "Thyroid hormone deficiency",
        "side_effects": "Weight loss, Palpitations",
        "dosage": "1 tablet before breakfast"
    },
    "Taxim-O": {
        "uses": "Bacterial infections",
        "side_effects": "Nausea, Diarrhea",
        "dosage": "1 tablet twice daily"
    },
    "Ulgel": {
        "uses": "Acidity, Gas",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Unienzyme": {
        "uses": "Indigestion",
        "side_effects": "None common",
        "dosage": "1 tablet after meals"
    },
    "Volini": {
        "uses": "Sprains, Back pain",
        "side_effects": "Skin redness",
        "dosage": "Apply gently on affected area"
    },
    "Vicks": {
        "uses": "Cough, Congestion",
        "side_effects": "Skin irritation",
        "dosage": "Rub on chest/throat"
    },
    "Wikoryl": {
        "uses": "Cold, Cough",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet twice daily"
    },
    "Wysolone": {
        "uses": "Inflammation, Allergies",
        "side_effects": "Weight gain, Mood swings",
        "dosage": "As directed by doctor"
    },
    "Xarelto": {
        "uses": "Blood thinner",
        "side_effects": "Bleeding",
        "dosage": "As prescribed"
    },
    "Xone": {
        "uses": "Bacterial infections",
        "side_effects": "Diarrhea, Nausea",
        "dosage": "As prescribed"
    },
    "Yondelis": {
        "uses": "Cancer treatment",
        "side_effects": "Fatigue, Vomiting",
        "dosage": "IV under supervision"
    },
    "Yogurt Sachets": {
        "uses": "Probiotic, Digestion",
        "side_effects": "None common",
        "dosage": "1 sachet daily"
    },
    "Zyrtec": {
        "uses": "Allergy, Sneezing",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet at bedtime"
    },
    "Zincovit": {
        "uses": "Immunity booster",
        "side_effects": "Mild stomach upset",
        "dosage": "1 tablet daily"
    }
}

# Health conditions and suggested medicines
HEALTH_CONDITIONS = {
    'stomach pain': ['Pantoprazole', 'Omez', 'Gelusil', 'Brufen', 'Flexon', 'Ibugesic', 'Meftal Spas'],
    'fever': ['Paracetamol', 'Dolo 650', 'Brufen', 'Flexon', 'Ibugesic', 'Fepanil', 'Jiffy'],
    'cold': ['Sinarest', 'Cetrizine', 'Benadryl', 'Honitus', 'Jiffy', 'Wikoryl', 'Vicks'],
    'headache': ['Paracetamol', 'Combiflam'],
    'allergy': ['Cetrizine', 'Zyrtec', 'Avil', 'Benadryl', 'Sinarest', 'Wysolone'],
    'acidity': ['Pantoprazole', 'Omez', 'Gelusil', 'Eno', 'Gaviscon', 'Junior Lanzol', 'Rantac', 'Ulgel'],
    'cough': ['Honitus', 'Benadryl', 'Sinarest', 'Wikoryl', 'Vicks'],
    'vomiting': ['Domstal', 'Ondem', 'Metrogyl', 'Taxim-O', 'Yondelis'],
    'skin irritation': ['Iodex', 'Soframycin', 'Quadriderm', 'Vicks', 'Wysolone']
}

# Regex patterns for extracting information
PATTERNS = {
    'brand_name': [
        # NEW: Specific patterns for real medicine strips
        r"(?i)\b(OLANZAC|OMIZOLE|BIFILAC|BILAC|PARACETAMOL|DOLO|CROCIN|COMBIFLAM)\b",  # Exact matches
        r"(?i)\b([A-Z][a-z]+(?:zole|zac|lac|flac|pril|olol|pine|mycin|cillin|floxacin))\b",  # Common suffixes
        r"(?i)\b([A-Z][A-Za-z]+)\s*&\s*([A-Z][A-Za-z]+)\b",  # "Olanzac & Omizole" format
        r"(?i)^([A-Z][a-z]+(?:\s\d{2,4})?)\b", # Covers names like "Evion 400" at the start
        r"(?i)\b([A-Z][a-z\s-]+)\s*(?:Tablet|Capsule|Syrup|Suspension|Injection|Cream|Gel|Ointment|Lotion|Powder|Drops)\b",
        r"(?i)\b([A-Z][a-z\s-]+)\s+\d+(?:mg|mcg|g|ml)\b",
        r"(?i)\b(\w+)\s+\d{2,4}(?:mg|mcg|g|ml)\b" # Generic capture for name and strength
    ],
    'generic_name': [
        r"(?i)\b(?:contains|each)\s+(.+?)(?:IP|BP|USP|Ph\.?Eur\.|\)|\n)", # Catches generic name before IP/BP/USP or end of line
        r"(?i)\b(Vitamin E|Tocopheryl Acetate)\b", # Specific for Vitamin E
        r"(?i)\b([A-Z][a-z\s-]+)\s+(?:BP|IP|USP|Ph\.?Eur)\b",
        r"(?i)\b(Lactic acid bacillus|Streptococcus faecalis|Clostridium butyricum|Lactobacillus sporogenes)\b" # Specific for other common generic names
    ],
    'uses': [
        r"(?i)\b(?:used for|uses|indications|for the treatment of|effective in)\s*[:-]?\s*(.+?)(?:\.|\n)",
        r"(?i)\b(?:treats|relieves|manages)\s+(.+?)(?:\.|\n)"
    ],
    'side_effects': [
        r"(?i)\b(?:side effects|adverse effects|warnings)\s*[:-]?\s*(.+?)(?:\.|\n)",
        r"(?i)\b(?:may cause|common side effects)\s*(.+?)(?:\.|\n)"
    ],
    'dosage': [
        r"(?i)\b(?:Dosage|Dose)\s*[:]?\s*(.+?)(?:\.|\n)", # Catches "Dosage: ..."
        r"(?i)(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:mg|mcg|g|ml)?(?:\/\s*(?:kg|day))?)\s+(?:daily|twice daily|thrice daily|as directed|once daily|every \d+ hours)",
        r"(?i)(\d+\s*(?:tablet|capsule|tsp|ml)s?\s*(?:daily|twice daily|thrice daily|as directed|once daily|every \d+ hours))",
        r"(?i)(?:One to two capsules thrice daily after)" # Specific for the given example
    ],
    'batch_number': [
        # NEW: Specific patterns for real strips (E40001, ALA306 formats)
        r"(?i)\b(?:B\.?\s*No\.?|Batch(?:\s*No\.?)?)\s*[:#-]?\s*([A-Z][0-9]{4,6})\b",  # E40001 format
        r"(?i)\b(?:B\.?\s*No\.?|Batch(?:\s*No\.?)?)\s*[:#-]?\s*([A-Z]{2,4}[0-9]{2,4})\b",  # ALA306 format
        r"(?i)\b(?:Batch(?:\s*No\.?|\s*Number)?|B\.?\s*No\.?|B\.?\s*N\.?|Lot(?:\s*No\.?|\s*Number)?)\s*[:#-]?\s*([A-Z0-9\-]+)\b"
    ],
    'mfd': [
        # NEW: Specific patterns for real strips (MFG. DT. JAN.24, MFD. 10/2023)
        r"(?i)MFG\.?\s*DT\.?\s*([A-Z]{3}\.?\s*\d{2,4})",  # MFG. DT. JAN.24
        r"(?i)MFD\.?\s*(\d{1,2}[./-]\d{2,4})",  # MFD. 10/2023
        r"(?i)MFG\.?\s*(?:Date)?\s*[:]??\s*(\d{1,2}[./-]\d{2,4}|[A-Za-z]{3}\.?\s*\d{4}|(?:19|20)\d{2})",
        r"(?i)(?:Mfd Date|Mfg Date|Manuf\.? Date)\.?\s*[:]??\s*(\d{1,2}[./-]\d{2,4}|[A-Za-z]{3}\s*\d{4}|(?:19|20)\d{2})\b"
    ],
    'expiry': [
        # NEW: Specific patterns for real strips (EXP. DT. DEC.26, EXP. 09/2025)
        r"(?i)EXP\.?\s*DT\.?\s*([A-Z]{3}\.?\s*\d{2,4})",  # EXP. DT. DEC.26
        r"(?i)EXP\.?\s*(\d{1,2}[./-]\d{2,4})",  # EXP. 09/2025
        r"(?i)EXP\.?\s*(?:Date)?\s*[:]??\s*(\d{1,2}[./-]\d{2,4}|[A-Za-z]{3}\.?\s*\d{4}|(?:19|20)\d{2})",
        r"(?i)(?:EXP|Exp Date|Expiry Date)\.?\s*[:]??\s*(\d{1,2}[./-]\d{2,4}|(?:19|20)\d{2})\b"
    ],
    'manufacturer': [
        r"(?i)(?:Manufactured by|Mfd\.? by|Mfg\.? by)\s*[:]?\s*(.+?)\b", # Capture until word boundary, allowing multiple words
        r"(?i)\b([A-Z][a-z\s&-]+(?:Ltd|Pvt\.? Ltd|Corp|Inc|Pharmaceuticals|Health Ltd|GmbH)?)\b"
    ],
    'mrp': [
        # NEW: Specific patterns for real strips (M.R.P. Rs. 189.00, M.R.P.Rs.140.00)
        r"(?i)M\.?R\.?P\.?\s*Rs\.?\s*(\d+(?:\.\d{2})?)",  # M.R.P. Rs. 189.00
        r"(?i)M\.?R\.?P\.?Rs\.?\s*(\d+(?:\.\d{2})?)",  # M.R.P.Rs.140.00 (no space)
        r"(?i)MRP\s*Rs\.?\s*(\d+(?:\.\d{2})?)", # Specifically for "MRP Rs.78.98"
        r"(?i)(?:MRP|M\.?R\.?P)\.?\s*[:]?\s*(?:Rs\.?|₹)\s*(\d+(?:[.,]\d{2})?)\b", # Generic MRP pattern
        r"(?i)₹(\d+(?:\.\d{2})?)" # Direct rupee symbol match
    ],
    'category': [
        r"(?i)\b(?:antibiotic|analgesic|antipyretic|anti-inflammatory|antihistamine|antacid|laxative|antifungal|antiviral|diuretic|hypnotic|sedative|antidepressant|anticoagulant|beta-blocker|statin|insulin|vaccine|hormone|vitamin)\b"
    ],
    'form': [
        r"(?i)\b(?:tablet|capsule|syrup|suspension|injection|cream|gel|ointment|lotion|powder|drops)\b"
    ]
}

# ─── Helper Functions ─────────────────────────────────────────────────────────
def get_medicine_suggestions(query):
    query = query.lower()
    suggestions = []
    # Iterate through all medicines in MEDICINE_INFO for partial matches
    for medicine_name, info in MEDICINE_INFO.items():
        if query in medicine_name.lower():
            suggestions.append({
                'name': medicine_name,
                'uses': info.get('uses', 'Information not available'),
                'side_effects': info.get('side_effects', 'Information not available')
            })
    return suggestions[:5]  # Return top 5 suggestions

def get_health_suggestions(condition):
    condition = condition.lower()
    suggested_medicines = []
    # Iterate through the conditions to find a match
    for key, medicines in HEALTH_CONDITIONS.items():
        if condition in key or key in condition:
            # If a match is found, retrieve detailed info for each suggested medicine
            for med_name in medicines:
                medicine_details = MEDICINE_INFO.get(med_name, {
                    'uses': 'Information not available',
                    'side_effects': 'Information not available',
                    'dosage': 'Please consult your doctor'
                })
                suggested_medicines.append({'name': med_name, **medicine_details})
    return suggested_medicines

# Cart helpers
def _get_cart():
    cart = session.get('cart') or {}
    # Ensure keys are strings to be JSON serializable in session
    return {str(k): int(v) for k, v in cart.items()}

def _save_cart(cart):
    session['cart'] = cart
    session.modified = True

# ─── Helper: Normalize vertical text ──────────────────────────────────────────
def normalize_vertical(text):
    lines = text.splitlines()
    normalized = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if len(line) == 1 and line.isalnum():
            run = [line]
            i += 1
            while i < len(lines) and len(lines[i].strip()) == 1 and lines[i].strip().isalnum():
                run.append(lines[i].strip())
                i += 1
            normalized.append("".join(run))
        else:
            normalized.append(line)
            i += 1
    return "\n".join(normalized)

# ─── Helper: Match from list of patterns ──────────────────────────────────────
def find_first_match(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            if len(match.groups()) > 0:
                return match.group(1).strip()
    return "Information not available"

def parse_date_flexible(date_str):
    """Parse various date formats commonly found on labels. Return date or None."""
    if not date_str:
        return None
    s = date_str.strip()
    # Fast reject placeholders
    if s.lower() in {"n/a", "na", "information not available", "unknown"}:
        return None
    fmts = [
        "%m/%Y", "%m-%Y", "%m.%Y", "%m/%y", "%m-%y",
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%b %Y", "%B %Y",
        "%Y",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            # If year-only, default to Jan 1st
            if fmt == "%Y":
                year = dt.year
                # Validate plausible range
                if 1990 <= year <= datetime.utcnow().year + 20:
                    return datetime(year, 1, 1).date()
                return None
            # Full/partial date parsed
            year = dt.year
            if 1990 <= year <= datetime.utcnow().year + 20:
                return dt.date()
            return None
        except Exception:
            continue
    # Try to extract MM and YYYY via regex like 02/26 or 02/2026
    m = re.search(r"(?i)\b(\d{1,2})[./-](\d{2,4})\b", s)
    if m:
        try:
            mm = int(m.group(1))
            yy = m.group(2)
            yyyy = int("20" + yy) if len(yy) == 2 else int(yy)
            if 1990 <= yyyy <= datetime.utcnow().year + 20:
                return datetime(yyyy, max(1, min(12, mm)), 1).date()
            return None
        except Exception:
            pass
    return None

# Collect all plausible dates from text for heuristic reconciliation
def find_date_candidates(text):
    candidates = []
    if not text:
        return candidates
    # Patterns: Month YYYY, MM/YYYY, MM-YYYY, and standalone valid years
    patterns = [
        r"(?i)\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b\d{1,2}[./-]\d{2,4}\b",
        r"\b(?:19|20)\d{2}\b",
    ]
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            raw = m.group(0).strip()
            if raw in seen:
                continue
            seen.add(raw)
            dt = parse_date_flexible(raw)
            if dt:
                candidates.append(dt)
    # Sort and dedupe
    candidates = sorted(set(candidates))
    return candidates

def add_months(d, months):
    if not d:
        return None
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, 28)
    try:
        return datetime(y, m, day).date()
    except Exception:
        return datetime(y, m, 1).date()

def shelf_life_months(text):
    if not text:
        return None
    m = re.search(r"(?i)\b(best\s*before|use\s*before|shelf\s*life)\s*(\d{1,2})\s*months?\b", text)
    if m:
        try:
            return int(m.group(2))
        except Exception:
            return None
    m = re.search(r"(?i)\b(\d{1,2})\s*months?\s*(?:from|after)\s*(?:mfg|manufacture|manufacturing)\b", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def reconcile_dates_from_text(full_text, mfd_dt, exp_dt):
    candidates = find_date_candidates(full_text)
    life = shelf_life_months(full_text)
    now = datetime.utcnow().date()
    if mfd_dt and exp_dt and exp_dt < mfd_dt:
        if len(candidates) >= 2:
            return min(candidates), max(candidates)
        return exp_dt, mfd_dt
    if mfd_dt and not exp_dt:
        if life:
            return mfd_dt, add_months(mfd_dt, life)
        later = [d for d in candidates if d > mfd_dt]
        if later:
            return mfd_dt, min(later)
        return mfd_dt, add_months(mfd_dt, 24)
    if exp_dt and not mfd_dt:
        earlier = [d for d in candidates if d < exp_dt]
        if earlier:
            return max(earlier), exp_dt
        if life:
            return add_months(exp_dt, -life), exp_dt
        return add_months(exp_dt, -24), exp_dt
    if not mfd_dt and not exp_dt:
        if len(candidates) >= 2:
            return min(candidates), max(candidates)
        if len(candidates) == 1:
            d = candidates[0]
            return d, add_months(d, 24)
        return now, add_months(now, 12)
    return mfd_dt, exp_dt

def _compile_date_regex():
    # Month name + year OR MM[/.-]YYYY or MM[/.-]YY (case-insensitive via flag)
    month = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    mmYY = r"\d{1,2}[./-]\d{2,4}"
    year = r"(?:19|20)\d{2}"
    return re.compile(rf"\b({month}|{mmYY}|{year})\b", re.IGNORECASE)

DATE_TOKEN_RE = _compile_date_regex()

def find_labeled_date_dt(text, keywords):
    """Find a date token near any of the given keywords within the same or next line.
    Returns a parsed date or None. Keeps changes local and robust for medicine strips."""
    if not text:
        return None
    lines = text.splitlines()
    # Build a case-insensitive search set
    kws = [k.lower() for k in keywords]
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in kws):
            # Avoid picking dates from license numbers like "Mfg Lic No: ... 2012"
            if "lic" in low or "license" in low:
                continue
            scope = line
            if i + 1 < len(lines):
                scope = scope + " " + lines[i + 1]
            # Try to find date token near the keyword
            m = DATE_TOKEN_RE.search(scope)
            if m:
                dt = parse_date_flexible(m.group(0))
                if dt:
                    return dt
            # If not found, try to combine month token and year token within a small window
            mon_re = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b", re.IGNORECASE)
            yr_re = re.compile(r"\b(?:19|20)\d{2}\b")
            mons = list(mon_re.finditer(scope))
            yrs = list(yr_re.finditer(scope))
            if mons and yrs:
                # pick closest year after a month within 12 chars
                for mon in mons:
                    for yr in yrs:
                        if yr.start() >= mon.end() and (yr.start() - mon.end()) <= 12:
                            candidate = scope[mon.start():yr.end()]
                            dt = parse_date_flexible(candidate)
                            if dt:
                                return dt
    # Fallback: window search after keyword anywhere in text
    low_text = text.lower()
    for k in kws:
        idx = low_text.find(k)
        if idx != -1:
            window = text[idx: idx + 120]
            m = DATE_TOKEN_RE.search(window)
            if m:
                dt = parse_date_flexible(m.group(0))
                if dt:
                    return dt
            # Combine month/year as above if needed
            mon_re = re.compile(r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b")
            yr_re = re.compile(r"\b(?:19|20)\d{2}\b")
            mons = list(mon_re.finditer(window))
            yrs = list(yr_re.finditer(window))
            if mons and yrs:
                for mon in mons:
                    for yr in yrs:
                        if yr.start() >= mon.end() and (yr.start() - mon.end()) <= 12:
                            candidate = window[mon.start():yr.end()]
                            dt = parse_date_flexible(candidate)
                            if dt:
                                return dt
    return None

# ─── OCR Helpers (Vision with Gemini fallback) ───────────────────────────────
def is_billing_disabled_error(e):
    try:
        msg = str(e)
        return ("BILLING_DISABLED" in msg) or ("requires billing" in msg.lower())
    except Exception:
        return False

def gemini_extract_text(image_content):
    try:
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not available for OCR fallback")
            return None

        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_api_key:
            logger.warning("No GEMINI_API_KEY set. Use FREE OCR instead: install Tesseract")
            return None

        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)

        # Open image
        from io import BytesIO
        import PIL.Image
        try:
            image_pil = PIL.Image.open(BytesIO(image_content))
        except Exception as img_err:
            logger.error(f"Gemini OCR: failed to open image: {img_err}")
            return None

        # Try preferred models
        preferred = ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']
        model = None
        for name in preferred:
            try:
                model = genai.GenerativeModel(name)
                break
            except Exception as me:
                logger.warning(f"Gemini OCR: could not init {name}: {me}")
                continue
        if model is None:
            logger.error("Gemini OCR: no model initialized")
            return None

        prompt = (
            "You are reading a medicine strip/blister pack. Read ALL text from the ENTIRE strip, including:\n\n"
            "1. MEDICINE NAME (CENTER/TOP of strip):\n"
            "   - Look in the CENTER area with reflective/metallic surface\n"
            "   - Large text, often in red or black\n"
            "   - Examples: 'Olanzac & Omizole', 'BIFILAC', 'Dolo-650', 'O2'\n"
            "   - May have '&' between two medicine names\n"
            "   - Read carefully even if surface is shiny/reflective\n\n"
            "2. BATCH NUMBER (BOTTOM area, often in BLUE/PURPLE stamp):\n"
            "   - Look for 'B.No.' or 'Batch' followed by code\n"
            "   - Format: E40001, ALA306, AM600/2012 (letters + numbers)\n"
            "   - Usually alphanumeric, 4-8 characters\n"
            "   - Often stamped in blue/purple ink\n\n"
            "3. MANUFACTURING DATE (BOTTOM area):\n"
            "   - Look for 'MFG. DT.' or 'MFD.' followed by date\n"
            "   - Format: JAN.24, 10/2023, FEB 2024\n"
            "   - Month abbreviation or number\n\n"
            "4. EXPIRY DATE (BOTTOM area):\n"
            "   - Look for 'EXP. DT.' or 'EXP.' followed by date\n"
            "   - Format: DEC.26, 09/2025, JAN 2026\n"
            "   - Month abbreviation or number\n\n"
            "5. MRP/PRICE (BOTTOM area):\n"
            "   - Look for 'M.R.P. Rs.' followed by price\n"
            "   - Format: Rs. 189.00, Rs.140.00\n"
            "   - Usually 10-999 rupees\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "- Read the MEDICINE NAME from the CENTER/TOP even if surface is reflective\n"
            "- Read the BATCH NUMBER from the BLUE/PURPLE stamp at bottom\n"
            "- Return ALL text exactly as it appears, preserving labels\n"
            "- Don't skip the medicine name - it's the most important!\n"
            "- Don't confuse batch numbers (E40001) with dates (JAN.24)\n"
            "- Don't confuse license numbers with MRP"
        )
        try:
            resp = model.generate_content([prompt, image_pil])
            text = (resp.text or '').strip()
            return text if text else None
        except Exception as api_err:
            logger.error(f"Gemini OCR: API error: {api_err}")
            return None
    except Exception as e:
        logger.error(f"Gemini OCR unexpected error: {e}")
        return None

def ocr_extract_text(image_content):
    """Extract text from image - PRIORITIZE Gemini AI for best accuracy on medicine strips."""
    
    # Check if Gemini API key is available
    try:
        gemini_key_present = bool(os.environ.get('GEMINI_API_KEY'))
    except Exception:
        gemini_key_present = False

    # Try Gemini API FIRST (best for medicine strips!)
    if GEMINI_AVAILABLE and gemini_key_present:
        logger.info("Attempting Gemini AI extraction (PRIORITY)...")
        text = gemini_extract_text(image_content)
        if text and len(text.strip()) > 50:  # Gemini should return substantial text
            logger.info(f"✓ Gemini AI successful! Extracted {len(text)} characters")
            return text
        else:
            logger.warning("Gemini AI returned insufficient text, trying local OCR...")
    
    # Try ADVANCED OCR as fallback
    if ADVANCED_OCR_AVAILABLE:
        logger.info("Attempting ADVANCED Strip OCR extraction...")
        try:
            advanced_ocr = get_advanced_ocr()
            text = advanced_ocr.extract_text_multiple_methods(image_content)
            if text and len(text.strip()) > 0:
                logger.info(f"✓ ADVANCED OCR successful! Extracted {len(text)} characters")
                return text
            else:
                logger.warning("ADVANCED OCR returned empty text, trying standard FREE OCR...")
        except Exception as e:
            logger.error(f"ADVANCED OCR failed: {e}")
            logger.info("Falling back to standard FREE OCR...")
    
    # Try standard FREE OCR
    if FREE_OCR_AVAILABLE:
        logger.info("Attempting standard FREE OCR extraction...")
        try:
            from free_ocr import FreeOCR
            ocr = FreeOCR()
            text = ocr.extract_text(image_content)
            if text and len(text.strip()) > 0:
                logger.info(f"✓ FREE OCR successful! Extracted {len(text)} characters")
                return text
            else:
                logger.warning("FREE OCR returned empty text, trying Vision API...")
        except Exception as e:
            logger.error(f"FREE OCR failed: {e}")
            logger.info("Falling back to Vision API...")
    else:
        logger.warning("FREE OCR not available. Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki")

    # Try Google Vision as last resort
    try:
        if global_vision_client:
            logger.info("Attempting Google Vision API extraction...")
            image = vision.Image(content=image_content)
            response = global_vision_client.text_detection(image=image)
            texts = response.text_annotations
            if texts:
                logger.info("✓ Google Vision successful!")
                return texts[0].description
        logger.warning("Vision OCR returned no text")
    except Exception as e:
        if is_billing_disabled_error(e):
            logger.error("Vision OCR billing disabled.")
        else:
            logger.error(f"Vision OCR error: {e}")

    # All methods failed
    logger.error("❌ All OCR methods failed!")
    logger.error("To fix: Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki")
    return None

def extract_fields_with_gemini_from_text(full_text):
    """Use Gemini to extract structured fields from OCR text. Returns dict or None."""
    try:
        if not GEMINI_AVAILABLE:
            return None
        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_api_key:
            return None
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        # Initialize a fast model
        model = None
        for name in ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']:
            try:
                model = genai.GenerativeModel(name)
                break
            except Exception:
                continue
        if model is None:
            return None
        prompt = (
            "You are an assistant that extracts medicine label fields from plain text. "
            "From the input, extract these fields when present: brand, dosage, batch_number, manufacture_date, expiry_date, manufacturer, mrp. "
            "Return ONLY a JSON object with keys: brand, dosage, batch_number, manufacture_date, expiry_date, manufacturer, mrp. "
            "Dates must be as seen on label (e.g., '02/2026' or 'Mar 2026'). If a field is missing, use an empty string."
        )
        resp = model.generate_content([prompt, full_text])
        text = (resp.text or '').strip()
        text = text.replace('```json', '').replace('```', '').strip()
        import json as _json
        try:
            data = _json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    data = _json.loads(m.group(0))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    return None
        return None
    except Exception:
        return None

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'HEAD'])
def landing_page():
    if 'user_type' in session:
        return redirect(url_for('index'))
    return render_template('landing.html')

@app.route('/login/owner', methods=['GET', 'POST'])
def login_owner():
    error = None
    if request.method == 'POST':
        name = request.form.get('name')
        secret = request.form.get('secret')
        if secret == '1111':
            session['logged_in'] = True
            session['user_type'] = 'owner'
            session['user_name'] = name
            return redirect(url_for('index'))
        else:
            error = 'Invalid secret code.'
    return render_template('login.html', error=error)

@app.route('/login/user', methods=['GET', 'POST'])
def login_user():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Allow any username and password for user login
        if username and password:
            session['logged_in'] = True
            session['user_type'] = 'user'
            session['user_name'] = username
            return redirect(url_for('index'))
        else:
            error = 'Please enter both username and password.'
    return render_template('user_login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing_page'))

@app.route('/chatbot', methods=['GET'])
def chatbot():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('chatbot.html')

@app.route('/bmi', methods=['GET', 'POST'])
def bmi_calculator():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))

    bmi_result = None
    error_message = None
    gender = None
    weight = None
    height = None

    if request.method == 'POST':
        try:
            gender = request.form.get('gender')
            weight = float(request.form.get('weight'))
            height = float(request.form.get('height'))

            if weight <= 0 or height <= 0:
                error_message = "Weight and height must be positive numbers."
            else:
                height_m = height / 100  # Convert cm to meters
                bmi = weight / (height_m ** 2)
                
                category = ""
                if bmi < 18.5:
                    category = "Underweight"
                elif 18.5 <= bmi < 25:
                    category = "Normal weight"
                elif 25 <= bmi < 30:
                    category = "Overweight"
                elif 30 <= bmi < 35:
                    category = "Obesity (Class I)"
                elif 35 <= bmi < 40:
                    category = "Obesity (Class II)"
                else:
                    category = "Extreme Obesity (Class III)"
                
                bmi_result = {
                    'bmi': f"{bmi:.2f}",
                    'category': category
                }

        except ValueError:
            error_message = "Invalid input. Please enter numeric values for weight and height."
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"

    return render_template('bmi_calculator.html', bmi_result=bmi_result, error_message=error_message, weight=weight, height=height, gender=gender)

@app.route('/health_tips', methods=['GET'])
def health_tips():
    if not session.get('logged_in'):
        return redirect(url_for('landing_page'))
    return render_template('health_tips.html')

# ─── User Feature Pages (no chatbot) ──────────────────────────────────────────
@app.route('/user/health-advice', methods=['GET'])
def health_advice_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('health_advice.html')

@app.route('/user/medicine-info', methods=['GET'])
def medicine_info_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('medicine_info_page.html')

@app.route('/user/availability-check', methods=['GET'])
def availability_check_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('availability_check_page.html')

@app.route('/user/upload-prescription', methods=['GET'])
def upload_prescription_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('upload_prescription_page.html')

# Shop & Cart Routes
@app.context_processor
def inject_cart_count():
    try:
        if session.get('user_type') != 'user':
            return dict(cart_count=0)
        cart = _get_cart()
        return dict(cart_count=sum(cart.values()))
    except Exception:
        return dict(cart_count=0)

@app.route('/shop', methods=['GET'])
def shop():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    query = request.args.get('q', '').strip().lower()
    medicines = Medicine.query.filter(Medicine.quantity > 0).all()
    if query:
        medicines = [m for m in medicines if query in m.medicine_name.lower() or query in m.brand.lower()]
    return render_template('shop.html', medicines=medicines, q=query)

@app.route('/cart', methods=['GET'])
def view_cart():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    cart = _get_cart()
    items = []
    total = 0.0
    for key, qty in cart.items():
        try:
            batch_id = int(key)
        except Exception:
            continue
        med = Medicine.query.get(batch_id)
        if not med:
            continue
        unit_price = float(med.price_per_unit)
        qty = max(0, min(qty, int(med.quantity)))
        subtotal = unit_price * qty
        total += subtotal
        items.append({
            'batch_id': med.batch_id,
            'name': med.medicine_name,
            'brand': med.brand,
            'price': unit_price,
            'qty': qty,
            'stock': int(med.quantity),
            'subtotal': subtotal
        })
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add', methods=['POST'])
def cart_add():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    batch_id = request.form.get('batch_id', type=int)
    qty = request.form.get('qty', type=int) or 1
    med = Medicine.query.get(batch_id)
    if not med or qty <= 0:
        flash('Invalid item.', 'danger')
        return redirect(url_for('shop'))
    if qty > int(med.quantity):
        qty = int(med.quantity)
    cart = _get_cart()
    current = cart.get(str(batch_id), 0)
    new_qty = min(current + qty, int(med.quantity))
    cart[str(batch_id)] = new_qty
    _save_cart(cart)
    flash(f'Added {new_qty} of {med.medicine_name} to cart.', 'success')
    return redirect(url_for('shop'))

@app.route('/cart/update', methods=['POST'])
def cart_update():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    batch_id = request.form.get('batch_id', type=int)
    qty = max(0, request.form.get('qty', type=int) or 0)
    med = Medicine.query.get(batch_id)
    cart = _get_cart()
    if not med:
        cart.pop(str(batch_id), None)
        _save_cart(cart)
        return redirect(url_for('view_cart'))
    if qty == 0:
        cart.pop(str(batch_id), None)
    else:
        cart[str(batch_id)] = min(qty, int(med.quantity))
    _save_cart(cart)
    return redirect(url_for('view_cart'))

@app.route('/cart/remove', methods=['POST'])
def cart_remove():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    batch_id = request.form.get('batch_id', type=int)
    cart = _get_cart()
    cart.pop(str(batch_id), None)
    _save_cart(cart)
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    cart = _get_cart()
    if not cart:
        batches = request.form.getlist('batches')
        quantities = request.form.getlist('quantities')
        if batches and quantities and len(batches) == len(quantities):
            tmp = {}
            for b, q in zip(batches, quantities):
                try:
                    bid = int(b); qty = int(q)
                except Exception:
                    continue
                if qty > 0:
                    tmp[str(bid)] = qty
            if tmp:
                cart = tmp
                _save_cart(cart)
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('view_cart'))
    items = []
    total = 0.0
    for key, qty in cart.items():
        batch_id = int(key)
        med = Medicine.query.get(batch_id)
        if not med or qty <= 0 or qty > int(med.quantity):
            flash('Stock changed, please review your cart.', 'warning')
            return redirect(url_for('view_cart'))
        unit_price = float(med.price_per_unit)
        subtotal = unit_price * qty
        total += subtotal
        items.append({
            'batch_id': med.batch_id,
            'name': med.medicine_name,
            'brand': med.brand,
            'price': unit_price,
            'qty': qty,
            'stock': int(med.quantity),
            'subtotal': subtotal
        })
    return render_template('payment.html', items=items, total=total)

@app.route('/checkout/confirm', methods=['POST'])
def checkout_confirm():
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    payment_method = request.form.get('payment_method', '').strip() or 'COD'
    cart = _get_cart()
    if not cart:
        batches = request.form.getlist('batches')
        quantities = request.form.getlist('quantities')
        if batches and quantities and len(batches) == len(quantities):
            tmp = {}
            for b, q in zip(batches, quantities):
                try:
                    bid = int(b); qty = int(q)
                except Exception:
                    continue
                if qty > 0:
                    tmp[str(bid)] = qty
            if tmp:
                cart = tmp
                _save_cart(cart)
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('view_cart'))
    items = []
    total = 0.0
    for key, qty in cart.items():
        batch_id = int(key)
        med = Medicine.query.get(batch_id)
        if not med or qty <= 0 or qty > int(med.quantity):
            flash('Stock changed, please review your cart.', 'warning')
            return redirect(url_for('view_cart'))
        subtotal = float(med.price_per_unit) * qty
        total += subtotal
        items.append((med, qty, subtotal))
    order = Order(user_name=session.get('user_name', 'Guest'), total_amount=total)
    db.session.add(order)
    db.session.flush()
    for med, qty, subtotal in items:
        db.session.add(OrderItem(
            order_id=order.id,
            medicine_batch_id=med.batch_id,
            medicine_name=med.medicine_name,
            quantity=qty,
            unit_price=float(med.price_per_unit),
            subtotal=subtotal
        ))
        med.quantity = int(med.quantity) - qty
    db.session.add(Payment(order_id=order.id, method=payment_method, status='success', amount=total))
    db.session.commit()
    session['cart'] = {}
    return redirect(url_for('order_success', order_id=order.id))

@app.route('/order/success/<int:order_id>')
def order_success(order_id):
    if not session.get('logged_in') or session.get('user_type') != 'user':
        return redirect(url_for('landing_page'))
    order = Order.query.get_or_404(order_id)
    items = OrderItem.query.filter_by(order_id=order.id).all()
    payment = Payment.query.filter_by(order_id=order.id).first()
    return render_template('order_success.html', order=order, items=items, payment=payment)

@app.route('/api/suggest', methods=['POST'])
def suggest():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    query = request.json.get('query', '').strip()
    if not query:
        return jsonify({'suggestions': []})
    
    suggestions = get_medicine_suggestions(query)
    return jsonify({'suggestions': suggestions})

@app.route('/api/health', methods=['POST'])
def health_advice():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        condition = request.json.get('query', '').strip()
        if not condition:
            return jsonify({'response': 'Please provide a health condition.'}), 400

        suggested_medicines = get_health_suggestions(condition)

        response_message = ""
        if suggested_medicines:
            # Ensure full HTML formatting with inline styles for ul and li for guaranteed rendering
            response_message = f"For <strong>{condition}</strong>, you might consider:<br><ul style=\"list-style: disc; margin-left: 20px; padding-left: 0; margin-top: 10px; text-align: left;\">"
            for med in suggested_medicines:
                response_message += f"<li style=\"margin-bottom: 5px; padding-left: 5px;\"><strong>{med['name']}</strong><br>Uses: {med['uses']}<br>Side Effects: {med['side_effects']}</li>"
            response_message += "</ul>"
        else:
            response_message = f"I don't have specific medicine suggestions for \"{condition}\" at the moment. Please consult a doctor."

        return jsonify({'response': response_message})

    except Exception as e:
        print(f"Error in /api/health: {e}")
        # traceback.print_exc() # Uncomment for debugging
        return jsonify({'response': 'Sorry, I encountered an error. Please try again.'}), 500

@app.route('/api/medicine-info', methods=['POST'])
def medicine_info():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        medicine_name = request.json.get('query', '').strip()
        if not medicine_name:
            return jsonify({'response': 'Please provide a medicine name.'}), 400

        # Search for medicine info case-insensitively
        found_medicine = None
        for name, info in MEDICINE_INFO.items():
            if name.lower() == medicine_name.lower():
                found_medicine = info
                found_medicine['name'] = name  # Store original name for display
                break

        response_message = ""
        if found_medicine:
            response_message = f"Information for <strong>{found_medicine['name']}</strong>:<br>"
            response_message += f"<div class=\"medicine-details\">"
            response_message += f"<p class=\"detail-item\"><strong>Uses:</strong> {found_medicine['uses']}</p>"
            response_message += f"<p class=\"detail-item\"><strong>Side Effects:</strong> {found_medicine['side_effects']}</p>"
            response_message += f"<p class=\"detail-item\"><strong>Dosage:</strong> {found_medicine['dosage']}</p>"
            response_message += "</div>"
        else:
            response_message = f"Sorry, I could not find information for \"{medicine_name}\". Please check the spelling or try another medicine."

        return jsonify({'response': response_message})

    except Exception as e:
        print(f"Error in /api/medicine-info: {e}")
        # traceback.print_exc() # Uncomment for debugging
        return jsonify({'response': 'Sorry, I encountered an error. Please try again.'}), 500

@app.route('/api/get_medicine_names')
def get_medicine_names():
    medicine_names = [med.medicine_name for med in Medicine.query.with_entities(Medicine.medicine_name).distinct().all()]
    return jsonify({'medicine_names': medicine_names})

@app.route('/api/check_medicine_availability', methods=['POST'])
def check_medicine_availability():
    data = request.json
    medicine_name = data.get('medicine_name', '')
    requested_quantity = data.get('quantity', 0)

    medicine = Medicine.query.filter(Medicine.medicine_name.ilike(medicine_name)).first()
    
    # Store the enquiry in database
    if session.get('user_type') == 'user':
        enquiry = MedicineEnquiry(
            medicine_name=medicine_name,
            quantity=requested_quantity,
            user_name=session.get('user_name', 'Anonymous')
        )
        db.session.add(enquiry)
        db.session.commit()
    
    response_message = ""
    if medicine:
        if medicine.quantity >= requested_quantity:
            total_price = medicine.price_per_unit * requested_quantity
            response_message = f"Yes, {medicine.medicine_name} is available. Price for {requested_quantity} units: ₹{{:.2f}}."
            response_message = response_message.format(total_price)
        else:
            response_message = f"Sorry, only {medicine.quantity} units of {medicine.medicine_name} are available in stock."
    else:
        response_message = f"Sorry, {medicine_name} is not found in our database."

    return jsonify({'response': response_message})

def check_medicine_availability_in_db(medicine_name):
    """Helper function to check medicine availability in database"""
    # Try exact match first
    medicine = Medicine.query.filter(Medicine.medicine_name.ilike(medicine_name)).first()
    
    # If not found, try partial match
    if not medicine:
        medicines = Medicine.query.filter(Medicine.medicine_name.ilike(f'%{medicine_name}%')).all()
        if medicines:
            medicine = medicines[0]  # Take the first match
    
    if medicine:
        return {
            'available': True,
            'name': medicine.medicine_name,
            'quantity': medicine.quantity,
            'price': medicine.price_per_unit
        }
    return {
        'available': False,
        'name': medicine_name,
        'quantity': 0,
        'price': 0.0
    }

def extract_medicines_with_gemini(image_content):
    """Extract medicine names from prescription image using Gemini API"""
    try:
        if not GEMINI_AVAILABLE:
            logger.error("Gemini API not available. Please install google-generativeai")
            return None
        
        # Initialize Gemini API - try environment variable first, then fallback
        gemini_api_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY not found in environment or fallback. Please set it.")
            return None
        
        logger.info(f"Using Gemini API key (starts with: {gemini_api_key[:10]}...)")
        
        genai.configure(api_key=gemini_api_key)
        # Try to find available models - prioritize newer models
        model = None
        
        # First, try to see what models are available
        try:
            available_models = [m.name for m in genai.list_models()]
            logger.info(f"Available models: {available_models[:10]}")
            
            # Prioritize flash models (faster) and stable versions
            preferred_models = [
                'models/gemini-2.0-flash',
                'models/gemini-2.5-flash',
                'models/gemini-2.5-pro',
                'models/gemini-2.0-flash-001',
            ]
            
            # Try preferred models first
            for preferred in preferred_models:
                if preferred in available_models:
                    try:
                        model = genai.GenerativeModel(preferred)
                        logger.info(f"Successfully initialized preferred model: {preferred}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to initialize {preferred}: {str(e)}")
                        continue
            
            # If preferred didn't work, try any gemini model
            if model is None:
                for available_model in available_models:
                    if 'gemini' in available_model.lower() and 'embedding' not in available_model.lower():
                        try:
                            model = genai.GenerativeModel(available_model)
                            logger.info(f"Successfully initialized model: {available_model}")
                            break
                        except Exception as e:
                            logger.warning(f"Failed to initialize {available_model}: {str(e)}")
                            continue
        except Exception as list_error:
            logger.warning(f"Could not list models: {str(list_error)}")
            # Fallback to known working models
            fallback_models = ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']
            for fallback in fallback_models:
                try:
                    model = genai.GenerativeModel(fallback)
                    logger.info(f"Successfully initialized fallback model: {fallback}")
                    break
                except Exception:
                    continue
        
        if model is None:
            raise Exception("Could not initialize any Gemini model. Please check your API key has access to Gemini models.")
        
        # Use Gemini to directly analyze the image (no need for Vision API - it requires billing)
        # Gemini can process images directly
        import PIL.Image
        from io import BytesIO
        
        try:
            # Convert image content to PIL Image
            image_pil = PIL.Image.open(BytesIO(image_content))
            logger.info(f"Image opened successfully: {image_pil.size}, mode: {image_pil.mode}")
        except Exception as img_error:
            logger.error(f"Failed to open image: {str(img_error)}")
            raise Exception(f"Could not process image: {str(img_error)}")
        
        # Use Gemini to extract medicine names directly from the image
        extraction_prompt = """Analyze this prescription image and extract all medicine names mentioned in it. 
        Return ONLY a JSON array of medicine names found in the prescription. 
        Format: ["Medicine Name 1", "Medicine Name 2", ...]
        If no medicines are found, return an empty array [].
        Do not include any other text, only the JSON array."""
        
        logger.info("Sending image directly to Gemini for analysis...")
        try:
            gemini_response = model.generate_content([extraction_prompt, image_pil])
            response_text = gemini_response.text.strip()
            logger.info(f"Gemini API response received (length: {len(response_text)})")
        except Exception as api_error:
            logger.error(f"Gemini API call failed: {str(api_error)}", exc_info=True)
            raise  # Re-raise to be caught by outer exception handler
        
        # Clean the response to extract JSON
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        try:
            medicines = json.loads(response_text)
            if isinstance(medicines, list):
                return medicines
            else:
                return []
        except json.JSONDecodeError:
            # Try to extract array from text
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if match:
                try:
                    medicines = json.loads(match.group(0))
                    return medicines if isinstance(medicines, list) else []
                except:
                    pass
            logger.error(f"Failed to parse Gemini response: {response_text}")
            return []
            
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error extracting medicines with Gemini: {error_details}", exc_info=True)
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_traceback}")
        
        # Check for common errors
        if "API key" in error_details or "authentication" in error_details.lower():
            logger.error("Possible API key authentication issue")
        elif "quota" in error_details.lower() or "limit" in error_details.lower():
            logger.error("Possible API quota/limit exceeded")
        elif "network" in error_details.lower() or "connection" in error_details.lower():
            logger.error("Possible network/connection issue")
        
        return None

def extract_medicines_with_chatgpt(image_content):
    """Extract medicine names from prescription image using ChatGPT API"""
    try:
        if not OPENAI_AVAILABLE:
            logger.error("OpenAI API not available. Please install openai")
            return None
        
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment. Please set it.")
            return None
        
        openai.api_key = openai_api_key
        
        # Convert image to base64
        image_base64 = base64.b64encode(image_content).decode('utf-8')
        
        # First, use Google Vision API to extract text (as fallback)
        image = vision.Image(content=image_content)
        texts = []
        if global_vision_client:
            response = global_vision_client.text_detection(image=image)
            texts = response.text_annotations
        if not texts:
            logger.warning("No text detected in prescription image")
            return []
        
        prescription_text = texts[0].description
        
        # Use ChatGPT to extract medicine names
        client = openai.OpenAI(api_key=openai_api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using cheaper model, can switch to gpt-4o for better accuracy
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical assistant. Extract medicine names from prescription text. Return ONLY a JSON array of medicine names."
                },
                {
                    "role": "user",
                    "content": f"""From the following prescription text, extract all medicine names. 
                    Return ONLY a JSON array of medicine names. Format: ["Medicine Name 1", "Medicine Name 2", ...]
                    If no medicines are found, return an empty array [].
                    Do not include any other text, only the JSON array.
                    
                    Prescription text:
                    {prescription_text}
                    """
                }
            ]
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean the response to extract JSON
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        try:
            # Try to parse as direct array first
            medicines = json.loads(response_text)
            if isinstance(medicines, list):
                return medicines
            
            # If it's a dict, try to extract array
            if isinstance(medicines, dict):
                medicines = medicines.get('medicines', medicines.get('medicine_names', []))
                if isinstance(medicines, list):
                    return medicines
            
            return []
        except json.JSONDecodeError:
            # Try to extract array from text using regex
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if match:
                try:
                    medicines = json.loads(match.group(0))
                    return medicines if isinstance(medicines, list) else []
                except:
                    pass
            logger.error(f"Failed to parse ChatGPT response: {response_text}")
            return []
            
    except Exception as e:
        logger.error(f"Error extracting medicines with ChatGPT: {str(e)}")
        return None

def extract_medicines_from_prescription(image_content):
    """Extract medicines from prescription using available methods (Free OCR, Gemini, or ChatGPT)"""
    # Debug logging
    gemini_key = os.environ.get('GEMINI_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')
    logger.info(f"FREE_OCR_AVAILABLE: {FREE_OCR_AVAILABLE}")
    logger.info(f"GEMINI_AVAILABLE: {GEMINI_AVAILABLE}, GEMINI_API_KEY available: {bool(gemini_key)}")
    logger.info(f"OPENAI_AVAILABLE: {OPENAI_AVAILABLE}, OPENAI_API_KEY available: {bool(openai_key)}")
    
    # Try FREE OCR first (no API costs!)
    if FREE_OCR_AVAILABLE:
        logger.info("Attempting to extract medicines with FREE OCR (EasyOCR/PaddleOCR/Tesseract)...")
        try:
            # Get known medicine names from database for better matching
            known_medicines = [med.medicine_name for med in Medicine.query.with_entities(Medicine.medicine_name).distinct().all()]
            
            medicines = extract_medicines_from_prescription_free(image_content, known_medicines)
            if medicines:
                logger.info(f"Successfully extracted {len(medicines)} medicines with FREE OCR: {medicines}")
                return medicines
            else:
                logger.warning("Free OCR extraction returned empty list - trying AI fallback")
        except Exception as e:
            logger.error(f"Exception in Free OCR extraction: {str(e)}", exc_info=True)
            logger.info("Falling back to AI-based extraction...")
    
    # Try Gemini as fallback
    if GEMINI_AVAILABLE:
        if gemini_key:
            logger.info("Attempting to extract medicines with Gemini...")
            try:
                medicines = extract_medicines_with_gemini(image_content)
                if medicines is not None:
                    logger.info(f"Successfully extracted {len(medicines)} medicines with Gemini")
                    return medicines
                else:
                    logger.warning("Gemini extraction returned None - check logs above for error details")
            except Exception as e:
                logger.error(f"Exception in Gemini extraction: {str(e)}", exc_info=True)
        else:
            logger.warning("Gemini available but no API key found")
    
    # Fallback to ChatGPT
    if OPENAI_AVAILABLE:
        if openai_key:
            logger.info("Attempting to extract medicines with ChatGPT...")
            try:
                medicines = extract_medicines_with_chatgpt(image_content)
                if medicines is not None:
                    logger.info(f"Successfully extracted {len(medicines)} medicines with ChatGPT")
                    return medicines
                else:
                    logger.warning("ChatGPT extraction returned None")
            except Exception as e:
                logger.error(f"Exception in ChatGPT extraction: {str(e)}", exc_info=True)
        else:
            logger.warning("OpenAI available but no API key found")
    
    # If all methods fail
    if not FREE_OCR_AVAILABLE:
        logger.error("No OCR method available! Install free OCR: pip install easyocr paddleocr pytesseract")
    logger.error("All extraction methods failed or unavailable")
    logger.error(f"FREE_OCR: {FREE_OCR_AVAILABLE}, GEMINI: {GEMINI_AVAILABLE}, OPENAI: {OPENAI_AVAILABLE}")
    return None

@app.route('/api/test_api_key', methods=['GET'])
def test_api_key():
    """Test endpoint to check API key configuration"""
    gemini_key = os.environ.get('GEMINI_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')
    
    result = {
        'GEMINI_AVAILABLE': GEMINI_AVAILABLE,
        'GEMINI_API_KEY_set': bool(gemini_key),
        'GEMINI_API_KEY_length': len(gemini_key) if gemini_key else 0,
        'GEMINI_API_KEY_preview': gemini_key[:10] + '...' if gemini_key else 'Not set',
        'OPENAI_AVAILABLE': OPENAI_AVAILABLE,
        'OPENAI_API_KEY_set': bool(openai_key),
        'using_fallback': not os.environ.get('GEMINI_API_KEY') and bool(GEMINI_API_KEY_FALLBACK)
    }
    
    # Try to actually call the API to test if it works
    if GEMINI_AVAILABLE and gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            
            # First, try to list available models
            try:
                available_models = [m.name for m in genai.list_models()]
                result['available_models'] = available_models[:10]  # First 10 models
            except Exception as list_error:
                result['list_models_error'] = str(list_error)
            
            # Try available models - prioritize flash models
            preferred_models = [
                'models/gemini-2.0-flash',
                'models/gemini-2.5-flash',
                'models/gemini-2.5-pro',
                'models/gemini-2.0-flash-001',
            ]
            
            model_worked = False
            # First try preferred models from available list
            for model_name in preferred_models:
                if model_name in available_models:
                    try:
                        model = genai.GenerativeModel(model_name)
                        test_response = model.generate_content("Say 'API test successful'")
                        result['api_test'] = 'SUCCESS'
                        result['api_response'] = test_response.text[:100] if test_response.text else 'No response'
                        result['model_used'] = model_name
                        model_worked = True
                        break
                    except Exception as model_error:
                        result[f'model_{model_name.replace("/", "_")}_error'] = str(model_error)[:200]
                        continue
            
            # If preferred didn't work, try any gemini model
            if not model_worked:
                for model_name in available_models:
                    if 'gemini' in model_name.lower() and 'embedding' not in model_name.lower():
                        try:
                            model = genai.GenerativeModel(model_name)
                            test_response = model.generate_content("Say 'API test successful'")
                            result['api_test'] = 'SUCCESS'
                            result['api_response'] = test_response.text[:100] if test_response.text else 'No response'
                            result['model_used'] = model_name
                            model_worked = True
                            break
                        except Exception as model_error:
                            continue
            
            if not model_worked:
                result['api_test'] = 'FAILED'
                result['api_error'] = 'All available models failed. Check model_*_error fields above.'
                result['error_type'] = 'AllModelsFailed'
                
        except Exception as e:
            result['api_test'] = 'FAILED'
            result['api_error'] = str(e)
            result['error_type'] = type(e).__name__
    
    return jsonify(result)

@app.route('/api/analyze_prescription', methods=['POST'])
def analyze_prescription():
    """Analyze prescription image and check medicine availability"""
    logger.info("=" * 50)
    logger.info("PRESCRIPTION UPLOAD REQUEST RECEIVED")
    logger.info("=" * 50)
    
    if not session.get('logged_in'):
        logger.warning("Unauthorized request - user not logged in")
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        logger.info("Checking for prescription file...")
        if 'prescription' not in request.files:
            logger.error("No 'prescription' key in request.files")
            return jsonify({'error': 'No prescription file provided'}), 400
        
        file = request.files['prescription']
        logger.info(f"File received: {file.filename if file else 'None'}")
        
        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        # Read image content
        logger.info("Reading image content...")
        image_content = file.read()
        logger.info(f"Image content size: {len(image_content)} bytes")
        
        if not image_content:
            logger.error("Empty image content")
            return jsonify({'error': 'Could not read file content'}), 400
        
        # Extract medicines using available API (Gemini or ChatGPT)
        logger.info("Starting prescription analysis...")
        medicines_list = extract_medicines_from_prescription(image_content)
        logger.info(f"Extraction result: {medicines_list}")
        
        if medicines_list is None:
            # Get more detailed error info
            gemini_key = os.environ.get('GEMINI_API_KEY')
            openai_key = os.environ.get('OPENAI_API_KEY')
            
            # Try a simple test to see what the actual error is
            test_error = None
            if GEMINI_AVAILABLE and gemini_key:
                try:
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel('models/gemini-2.0-flash')
                    test_response = model.generate_content("test")
                    test_error = "API works but extraction failed - check Flask logs"
                except Exception as test_ex:
                    test_error = f"API test failed: {str(test_ex)}"
            
            error_msg = f'Failed to process prescription. '
            error_msg += f'GEMINI_AVAILABLE: {GEMINI_AVAILABLE}, Has key: {bool(gemini_key)}, '
            error_msg += f'OPENAI_AVAILABLE: {OPENAI_AVAILABLE}, Has key: {bool(openai_key)}. '
            if test_error:
                error_msg += f'Diagnostic: {test_error}. '
            error_msg += 'Please check the Flask app terminal for detailed error logs.'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
        
        if not medicines_list:
            return jsonify({'medicines': []})
        
        # Check availability for each medicine
        results = []
        for med_name in medicines_list:
            availability = check_medicine_availability_in_db(med_name)
            results.append({
                'name': availability['name'],
                'available': availability['available'],
                'quantity': availability['quantity'],
                'price': availability['price']
            })
        
        return jsonify({'medicines': results})
        
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error analyzing prescription: {error_details}", exc_info=True)
        import traceback
        full_trace = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_trace}")
        
        # Return more detailed error to user
        user_error = f'Error processing prescription: {error_details}'
        if len(error_details) > 200:
            user_error = error_details[:200] + "... (see Flask logs for full error)"
        
        return jsonify({'error': user_error}), 500

@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        logger.info("POST request received for image upload")
        
        # Check if file is in request
        if 'image' not in request.files:
            logger.error("No 'image' in request.files")
            return render_template('index.html', error_message="❌ No file part in request")
        
        file = request.files['image']
        logger.info(f"File received: {file.filename if file else 'None'}")
        
        if not file or file.filename == '':
            logger.error("No selected file")
            return render_template('index.html', error_message="❌ No file selected")
        
        try:
            # Read and OCR the image - FIX: Store content to avoid buffering issues
            logger.info("Reading image content")
            image_content = file.read()
            if not image_content:
                logger.error("No content read from file")
                return render_template('index.html', error_message="❌ Could not read file content")
            
            # Reset file pointer for potential re-reads (though we use image_content now)
            file.seek(0)
            
            logger.info("Performing OCR with Gemini AI priority")
            
            # Extract text using Gemini first (fastest and most accurate)
            full_text = ocr_extract_text(image_content)
            
            # Try advanced OCR only if Gemini didn't work
            advanced_info = None
            if not full_text or len(full_text.strip()) < 50:
                if ADVANCED_OCR_AVAILABLE:
                    try:
                        logger.info("Gemini returned insufficient text, trying advanced OCR...")
                        advanced_info = process_medicine_strip_image(image_content)
                        if advanced_info:
                            logger.info(f"Advanced OCR extracted: {advanced_info}")
                    except Exception as e:
                        logger.error(f"Advanced OCR failed: {e}")
            if not full_text:
                return render_template(
                    'index.html',
                    error_message=(
                        "❌ OCR failed. Either enable Google Vision billing or set GEMINI_API_KEY "
                        "for fallback and retry."
                    )
                )
            logger.info(f"OCR Text extracted: {full_text[:100]}...")  # Log first 100 chars
            
            full_text = normalize_vertical(full_text)

            # Use advanced OCR results if available, otherwise use regex
            if advanced_info and isinstance(advanced_info, dict):
                brand = advanced_info.get('medicine_name') or find_first_match(full_text, PATTERNS['brand_name'])
                batch = advanced_info.get('batch_number') or find_first_match(full_text, PATTERNS['batch_number'])
                mfd_date = advanced_info.get('manufacture_date') or find_first_match(full_text, PATTERNS['mfd'])
                exp_date = advanced_info.get('expiry_date') or find_first_match(full_text, PATTERNS['expiry'])
                mrp_str = str(advanced_info.get('mrp', '')) if advanced_info.get('mrp') else find_first_match(full_text, PATTERNS['mrp'])
                dosage = find_first_match(full_text, PATTERNS['dosage'])
                manufacturer = find_first_match(full_text, PATTERNS['manufacturer'])
                logger.info(f"Using advanced OCR results: brand={brand}, batch={batch}, mfd={mfd_date}, exp={exp_date}, mrp={mrp_str}")
            else:
                # Extract fields (regex first)
                brand = find_first_match(full_text, PATTERNS['brand_name'])
                dosage = find_first_match(full_text, PATTERNS['dosage'])
                batch = find_first_match(full_text, PATTERNS['batch_number'])
                mfd_date = find_first_match(full_text, PATTERNS['mfd'])
                exp_date = find_first_match(full_text, PATTERNS['expiry'])
                manufacturer = find_first_match(full_text, PATTERNS['manufacturer'])
                mrp_str = find_first_match(full_text, PATTERNS['mrp'])

            # Try Gemini structured extraction and merge (only if advanced OCR didn't find data)
            try:
                gem_fields = extract_fields_with_gemini_from_text(full_text)
            except Exception:
                gem_fields = None
            if isinstance(gem_fields, dict):
                def pick(primary, alt):
                    return primary if primary and str(primary).strip() and str(primary).strip() != "Information not available" else alt
                
                # Only use Gemini if advanced OCR didn't find it
                if not brand or brand == "Information not available":
                    brand = pick(gem_fields.get('brand'), brand)
                if not dosage or dosage == "Information not available":
                    dosage = pick(gem_fields.get('dosage'), dosage)
                
                # Batch: validate it's not a date (like JAN24)
                if not batch or batch == "Information not available":
                    candidate_batch = gem_fields.get('batch_number')
                    if candidate_batch and candidate_batch.strip():
                        import re as _re
                        # Reject if it looks like a date (JAN24, FEB25, etc.)
                        if not _re.match(r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$', candidate_batch.strip().upper()):
                            if _re.search(r"[A-Za-z]", candidate_batch) and _re.search(r"\d", candidate_batch) and len(candidate_batch.strip()) >= 4:
                                if not brand or candidate_batch.strip().lower() != str(brand).strip().lower():
                                    batch = candidate_batch.strip()
                
                # Dates: only use if not already found
                if not mfd_date or mfd_date == "Information not available":
                    mfd_candidate = gem_fields.get('manufacture_date')
                    if mfd_candidate and str(mfd_candidate).strip():
                        mfd_date = str(mfd_candidate).strip()
                if not exp_date or exp_date == "Information not available":
                    exp_candidate = gem_fields.get('expiry_date')
                    if exp_candidate and str(exp_candidate).strip():
                        exp_date = str(exp_candidate).strip()
                
                if not manufacturer or manufacturer == "Information not available":
                    manufacturer = pick(gem_fields.get('manufacturer'), manufacturer)
                
                # MRP: validate it's reasonable (not 158100!)
                if not mrp_str or mrp_str == "Information not available":
                    gem_mrp = gem_fields.get('mrp')
                    if gem_mrp:
                        try:
                            import re as _re
                            # Extract just the number
                            mrp_match = _re.search(r'([0-9]+\.?[0-9]*)', str(gem_mrp))
                            if mrp_match:
                                mrp_val = float(mrp_match.group(1))
                                # Only accept if reasonable (10-999 Rs)
                                if 10 <= mrp_val <= 999:
                                    mrp_str = str(gem_mrp)
                        except:
                            pass

            logger.info(f"Merged fields: Brand={brand}, Dosage={dosage}, Batch={batch}, MFD={mfd_date}, EXP={exp_date}, Manufacturer={manufacturer}, MRP={mrp_str}")

            # Fallback batch: any 6+ digit number
            if not batch:
                m = re.search(r'(\d{6,})', full_text)
                batch = m.group(1) if m else None

            # Parse MRP robustly
            try:
                import re as _re
                mrp_val = 0.0
                if mrp_str:
                    m = _re.search(r"(\d+(?:[.,]\d{1,2})?)", str(mrp_str))
                    if m:
                        mrp_val = float(m.group(1).replace(',', ''))
            except Exception:
                mrp_val = 0.0

            # Parse dates and reconcile using heuristics
            mfd_dt = None
            exp_dt = None
            # Prefer dates next to explicit labels first (avoids picking years from license lines)
            try:
                labeled_mfd = find_labeled_date_dt(full_text, ['mfg', 'mfg.', 'mfd', 'manufactured'])
                labeled_exp = find_labeled_date_dt(full_text, ['exp', 'exp.', 'expiry', 'use before', 'best before'])
            except Exception:
                labeled_mfd = None
                labeled_exp = None
            if labeled_mfd:
                mfd_dt = labeled_mfd
            if labeled_exp:
                exp_dt = labeled_exp
            # Fall back to regex-extracted date strings
            if not mfd_dt and mfd_date and mfd_date != 'Information not available':
                mfd_dt = parse_date_flexible(mfd_date)
            if not exp_dt and exp_date and exp_date != 'Information not available':
                exp_dt = parse_date_flexible(exp_date)

            # Reconcile with OCR text context (handles swapped/missing)
            mfd_dt, exp_dt = reconcile_dates_from_text(full_text, mfd_dt, exp_dt)

            # Provide safe defaults if still missing
            if not mfd_dt:
                mfd_dt = datetime.utcnow().date()
            if not exp_dt:
                exp_dt = add_months(mfd_dt, 12)

            # Ensure EXP is after MFD
            if exp_dt < mfd_dt:
                exp_dt = add_months(mfd_dt, 12)

            # Save to DB
            med = Medicine(
                medicine_name = brand or "N/A",
                brand = brand or "N/A",
                category = "N/A",
                batch_number = batch or "N/A",
                quantity = 0,
                price_per_unit = mrp_val,
                manufacture_date = mfd_dt,
                expiry_date = exp_dt
            )
            db.session.add(med)
            db.session.commit()
            logger.info("Medicine record saved to database")

            # Build result
            mfd_display = mfd_dt.strftime("%b %Y") if mfd_dt else 'N/A'
            exp_display = exp_dt.strftime("%b %Y") if exp_dt else 'N/A'
            result = {
                'brand': brand or 'N/A',
                'dosage': dosage or 'N/A',
                'batch': batch or 'N/A',
                'mfd_date': mfd_display,
                'exp_date': exp_display,
                'manufacturer': manufacturer or 'N/A',
                'mrp_val': f"{mrp_val:.2f}"
            }

            # Cross-verify: fetch last known price for same brand (if any)
            prev_price = None
            try:
                if brand:
                    last_med = Medicine.query.filter(Medicine.medicine_name.ilike(brand)).order_by(Medicine.batch_id.desc()).first()
                    if last_med and last_med.price_per_unit:
                        prev_price = float(last_med.price_per_unit)
            except Exception:
                prev_price = None

            return render_template('index.html', result=result, prev_price=prev_price)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}", exc_info=True)
            return render_template('index.html', error_message=f"❌ Error processing image: {str(e)}")

    return render_template('index.html')

@app.route('/save_ocr', methods=['POST'])
def save_ocr():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    try:
        brand = request.form.get('brand') or 'N/A'
        dosage = request.form.get('dosage') or 'N/A'
        batch_number = request.form.get('batch') or request.form.get('batch_number') or 'N/A'
        manufacturer = request.form.get('manufacturer') or 'N/A'
        mrp_input = request.form.get('mrp') or request.form.get('mrp_val') or ''
        mfd_input = request.form.get('mfd_date') or request.form.get('mfd') or ''
        exp_input = request.form.get('exp_date') or request.form.get('exp') or ''

        # Price parsing with fallback to last known price for this brand
        mrp_val = 0.0
        if mrp_input:
            m = re.search(r"(\d+(?:[.,]\d{1,2})?)", mrp_input)
            if m:
                try:
                    mrp_val = float(m.group(1).replace(',', ''))
                except Exception:
                    mrp_val = 0.0
        if mrp_val == 0.0 and brand:
            last = Medicine.query.filter(Medicine.medicine_name.ilike(brand)).order_by(Medicine.batch_id.desc()).first()
            if last and last.price_per_unit:
                mrp_val = float(last.price_per_unit)

        # Dates: parse input flexibly; ensure EXP after MFD
        mfd_dt = parse_date_flexible(mfd_input) if mfd_input else None
        exp_dt = parse_date_flexible(exp_input) if exp_input else None
        mfd_dt, exp_dt = reconcile_dates_from_text("" , mfd_dt, exp_dt)
        if not mfd_dt:
            mfd_dt = datetime.utcnow().date()
        if not exp_dt or exp_dt < mfd_dt:
            exp_dt = add_months(mfd_dt, 12)

        # Upsert by batch_number when available; otherwise create new
        med = None
        if batch_number and batch_number != 'N/A':
            med = Medicine.query.filter(Medicine.batch_number == batch_number).first()

        if med:
            med.medicine_name = brand
            med.brand = brand
            med.category = med.category or 'N/A'
            med.batch_number = batch_number
            med.quantity = med.quantity or 0
            med.price_per_unit = mrp_val
            med.manufacture_date = mfd_dt
            med.expiry_date = exp_dt
        else:
            med = Medicine(
                medicine_name=brand,
                brand=brand,
                category='N/A',
                batch_number=batch_number or 'N/A',
                quantity=0,
                price_per_unit=mrp_val,
                manufacture_date=mfd_dt,
                expiry_date=exp_dt
            )
            db.session.add(med)

        db.session.commit()
        flash('Medicine details verified and saved successfully.', 'success')
        return redirect(url_for('medicine_database'))
    except Exception as e:
        logger.error(f"Error saving verified OCR data: {e}", exc_info=True)
        flash(f'Failed to save: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/owner/add_medicine', methods=['GET', 'POST'])
def add_medicine():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    if request.method == 'POST':
        try:
            medicine_name = request.form['medicine_name']
            brand = request.form['brand']
            category = request.form['category']
            batch_number = request.form['batch_number']
            quantity = int(request.form['quantity'])
            price_per_unit = float(request.form['price_per_unit'])
            manufacture_date_str = request.form['manufacture_date']
            expiry_date_str = request.form['expiry_date']

            manufacture_date = datetime.strptime(manufacture_date_str, '%Y-%m-%d').date()
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            
            # Find the next available batch_id
            last_medicine = Medicine.query.order_by(Medicine.batch_id.desc()).first()
            next_batch_id = (last_medicine.batch_id + 1) if last_medicine else 1

            new_medicine = Medicine(
                batch_id=next_batch_id,
                medicine_name=medicine_name,
                brand=brand,
                category=category,
                batch_number=batch_number,
                quantity=quantity,
                price_per_unit=price_per_unit,
                manufacture_date=manufacture_date,
                expiry_date=expiry_date
            )

            db.session.add(new_medicine)
            db.session.commit()
            flash(f'Medicine \'{medicine_name}\' added successfully!', 'success')
            return redirect(url_for('medicine_database'))
        except ValueError:
            flash('Invalid input for quantity or price. Please enter valid numbers.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')

    return render_template('add_medicine.html')

@app.route('/owner/medicines')
def medicine_database():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    from datetime import datetime, timedelta
    
    # Get all medicines
    medicines = Medicine.query.all()
    current_date = datetime.utcnow().date()
    six_months_later = current_date + timedelta(days=180)
    
    # Debug logging
    print(f"Current date: {current_date}")
    print(f"Six months later: {six_months_later}")
    
    expiring_medicines = []
    low_stock_medicines = []
    
    # Check each medicine's expiry date
    for med in medicines:
        # Convert string date to date object if needed
        if isinstance(med.expiry_date, str):
            med.expiry_date = datetime.strptime(med.expiry_date, '%Y-%m-%d').date()
        
        days_until_expiry = (med.expiry_date - current_date).days
        is_expiring_soon = med.expiry_date <= six_months_later
        
        # Add attributes to medicine object
        med.is_expiring_soon = is_expiring_soon
        med.days_until_expiry = days_until_expiry
        
        if is_expiring_soon:
            expiring_medicines.append({
                'name': med.medicine_name,
                'batch': med.batch_number,
                'expiry_date': med.expiry_date,
                'days_left': days_until_expiry
            })
        
        # Low stock threshold
        if isinstance(med.quantity, int) and med.quantity < 50:
            low_stock_medicines.append({
                'name': med.medicine_name,
                'batch': med.batch_number,
                'quantity': med.quantity
            })
    
    # Debug logging
    print(f"Found {len(expiring_medicines)} medicines expiring within 6 months")
    for med in expiring_medicines:
        print(f"- {med['name']} (Batch: {med['batch']}): {med['days_left']} days left (expires {med['expiry_date']})")
    
    # Sort medicines by expiry date (soonest first)
    medicines.sort(key=lambda x: x.expiry_date)
    
    return render_template('medicine_database.html',
                         medicines=medicines,
                         show_alert=len(expiring_medicines) > 0,
                         expiring_meds=expiring_medicines[:10],
                         show_low_stock_alert=len(low_stock_medicines) > 0,
                         low_stock_meds=low_stock_medicines[:10])  # Show top items

# Inject global alert counts for owner navbar badges
@app.context_processor
def inject_alert_counts():
    try:
        if session.get('user_type') != 'owner':
            return dict(expiring_count=0, low_stock_count=0)
        current_date = datetime.utcnow().date()
        six_months_later = current_date + timedelta(days=180)
        expiring_count = Medicine.query.filter(Medicine.expiry_date <= six_months_later).count()
        low_stock_count = Medicine.query.filter(Medicine.quantity < 50).count()
        return dict(expiring_count=expiring_count, low_stock_count=low_stock_count)
    except Exception:
        return dict(expiring_count=0, low_stock_count=0)

@app.route('/owner/alerts')
def owner_alerts():
    if not session.get('logged_in') or session.get('user_type') != 'owner':
        return jsonify({'error': 'Unauthorized'}), 403
    current_date = datetime.utcnow().date()
    six_months_later = current_date + timedelta(days=180)
    medicines = Medicine.query.all()
    expiring = []
    low_stock = []
    for med in medicines:
        exp_date = med.expiry_date
        if isinstance(exp_date, str):
            exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
        if exp_date <= six_months_later:
            expiring.append({
                'name': med.medicine_name,
                'batch': med.batch_number,
                'expiry_date': exp_date.strftime('%Y-%m-%d'),
                'days_left': (exp_date - current_date).days
            })
        if isinstance(med.quantity, int) and med.quantity < 50:
            low_stock.append({
                'name': med.medicine_name,
                'batch': med.batch_number,
                'quantity': med.quantity
            })
    # Sort by days_left ascending for expiring
    expiring.sort(key=lambda x: x['days_left'])
    return jsonify({
        'expiring_count': len(expiring),
        'low_stock_count': len(low_stock),
        'expiring': expiring[:10],
        'low_stock': low_stock[:10]
    })

@app.route('/owner/enquiries')
def view_enquiries():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    # Ensure the table exists when accessing this page
    with app.app_context():
        db.create_all()
    
    enquiries = MedicineEnquiry.query.order_by(MedicineEnquiry.enquiry_date.desc()).all()
    return render_template('enquiries.html', enquiries=enquiries)

@app.route('/api/process_medicine_strip', methods=['POST'])
def process_medicine_strip():
    """Process medicine strip image with advanced OCR for better accuracy"""
    logger.info("=" * 50)
    logger.info("MEDICINE STRIP PROCESSING REQUEST")
    logger.info("=" * 50)
    
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # FIX: Read image content once and store it to avoid buffering issues
        image_content = file.read()
        if not image_content:
            return jsonify({'error': 'Could not read file content'}), 400
        
        # Reset file pointer in case it's needed again
        file.seek(0)
        
        logger.info(f"Processing medicine strip image ({len(image_content)} bytes)")
        
        # Use advanced OCR for medicine strips
        if ADVANCED_OCR_AVAILABLE:
            try:
                result = process_medicine_strip_image(image_content)
                if result and isinstance(result, dict):
                    logger.info(f"Advanced OCR extracted: {result}")
                    return jsonify({
                        'success': True,
                        'data': result
                    })
                else:
                    logger.warning("Advanced OCR returned no results")
            except Exception as e:
                logger.error(f"Advanced OCR failed: {e}")
        
        # Fallback to standard OCR
        logger.info("Falling back to standard OCR...")
        try:
            text = ocr_extract_text(image_content)
            if text and len(text.strip()) > 10:
                return jsonify({
                    'success': True,
                    'data': {
                        'raw_text': text
                    }
                })
        except Exception as e:
            logger.error(f"Standard OCR failed: {e}")
        
        return jsonify({'error': 'Failed to extract text from image'}), 500
        
    except Exception as e:
        logger.error(f"Error processing medicine strip: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Log API key status on startup
    gemini_key = os.environ.get('GEMINI_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')
    logger.info("=" * 50)
    logger.info("Starting Flask application...")
    logger.info(f"GEMINI_AVAILABLE: {GEMINI_AVAILABLE}")
    logger.info(f"GEMINI_API_KEY set: {bool(gemini_key)}")
    if gemini_key:
        logger.info(f"GEMINI_API_KEY starts with: {gemini_key[:10]}...")
    logger.info(f"OPENAI_AVAILABLE: {OPENAI_AVAILABLE}")
    logger.info(f"OPENAI_API_KEY set: {bool(openai_key)}")
    logger.info("=" * 50)
    
    with app.app_context():
        db.create_all()  # This will create all tables including MedicineEnquiry
        # Check if the database is empty before populating
        if not Medicine.query.first():
            for data in initial_medicine_data:
                data['manufacture_date'] = datetime.strptime(data['manufacture_date'], '%Y-%m-%d').date()
                data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                medicine = Medicine(**data)
                db.session.add(medicine)
            db.session.commit()
    app.run(debug=True)