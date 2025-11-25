# Smart Medicine Management System (AI + OCR)

A Flask-based web app for managing medicines, extracting data from prescriptions using Google Cloud Vision OCR with optional AI parsing, owner inventory alerts, and a full shopping experience with cart and a payment selection step.

## Features
- Owner portal: add/view medicines, database management
- OCR upload for prescriptions (Google Cloud Vision)
- AI parsing for medicine info (Gemini/OpenAI optional)
- Expiry and low-stock alerts (bell dropdown)
- User portal: shop, add to cart, update/remove items
- Checkout with payment selection (COD/UPI/Card placeholder)
- Orders and order summary page

## Tech Stack
- Python, Flask, Jinja2
- SQLite via Flask-SQLAlchemy
- Google Cloud Vision API (OCR)
- Optional: Google Generative AI (Gemini) or OpenAI for parsing
- Bootstrap 5, Font Awesome

## Prerequisites
- Python 3.10+
- Google Cloud service account key for Vision API (JSON file)
- Optionally, Gemini or OpenAI API keys if you enable AI parsing

## Quick Start
1) Create and activate a virtual environment
```
python -m venv venv
./venv/Scripts/activate  # Windows
```

2) Install dependencies
```
pip install -r "main medicine_ocr updated/requirements.txt"
```

3) Set up credentials
- Place your Google service account key file locally (e.g. `vision-key.json`).
- Do NOT commit this file. It is ignored via `.gitignore`.
- Set an environment variable so the Vision client can authenticate:
```
set GOOGLE_APPLICATION_CREDENTIALS=\full\path\to\vision-key.json   # Windows CMD
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\\full\\path\\vision-key.json"  # PowerShell
```
- Optional AI keys (only if you use those features):
```
set GOOGLE_API_KEY=your_gemini_api_key
set OPENAI_API_KEY=your_openai_api_key
```

4) Run the app
```
cd "main medicine_ocr updated"
set FLASK_APP=app.py
flask run
```
Open http://127.0.0.1:5000/ in the browser.

## Default Access
- Owner secret: `1111` (defined in app logic)
- App secret key: configured in `app.py` for sessions

## Database
- SQLite files live under `main medicine_ocr updated/instance` and are ignored by git.
- Tables are auto-created on app start. If needed, delete the DB file(s) to reset.

## Shopping & Payment Flow
- Add items in Shop → View Cart → Place Order → Payment selection (COD/UPI/Card)
- On confirm, order is created, stock is updated, and an order success page is shown.
- Payment integrations are placeholders; you can integrate a real gateway (Razorpay/Stripe/PayPal) next.

## Security Notes
- `.gitignore` excludes `vision-key.json`, DB files, venv, and system artifacts.
- Never commit credentials. If a key leaks, rotate it immediately in Google Cloud Console.

## Project Structure (key files)
```
main medicine_ocr updated/
  app.py                      # Flask app, routes, models
  requirements.txt            # Python dependencies
  templates/                  # Jinja templates (shop, cart, payment, success, etc.)
  instance/                   # SQLite DB files (ignored)
```

## Next Steps
- Add README badges/screenshots
- Integrate a real payment gateway (optional)
- Deploy to a platform (Render/Heroku/railway)

## License
Specify your preferred license here.
