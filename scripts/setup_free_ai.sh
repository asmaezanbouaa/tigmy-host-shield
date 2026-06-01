#!/bin/bash
# Setup free AI for guest ID verification (no cloud quota needed)
set -e
cd "$(dirname "$0")/.."

echo "=== Local OCR (recommended — unlimited, no daily quota) ==="
echo "Install Tesseract (Ubuntu/Debian):"
echo "  sudo apt install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng"
echo ""
.venv/bin/pip install -q pytesseract 2>/dev/null || pip install pytesseract
echo "Add to .env:"
echo "  AI_PROVIDER=local"
echo ""
echo "Restart app: ./run.sh"
