import os
import sys

BASE_DIR = os.path.dirname(__file__)
APP_DIR = os.path.join(BASE_DIR, "main medicine_ocr updated")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app as application
