import os
import importlib.util
from jinja2 import FileSystemLoader

BASE_DIR = os.path.dirname(__file__)
SUB_APP_PATH = os.path.join(BASE_DIR, "main medicine_ocr updated", "app.py")

spec = importlib.util.spec_from_file_location("subapp", SUB_APP_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Expose the Flask app for Gunicorn: gunicorn app:app
app = getattr(module, "app")

# Ensure Jinja templates directory is correctly resolved in deployment
templates_path = os.path.join(BASE_DIR, "main medicine_ocr updated", "templates")
app.jinja_loader = FileSystemLoader(templates_path)
