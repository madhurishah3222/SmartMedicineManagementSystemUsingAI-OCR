import os
import importlib.util

BASE_DIR = os.path.dirname(__file__)
SUB_APP_PATH = os.path.join(BASE_DIR, "main medicine_ocr updated", "app.py")

spec = importlib.util.spec_from_file_location("subapp", SUB_APP_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Expose the Flask app for Gunicorn: gunicorn app:app
app = getattr(module, "app")
