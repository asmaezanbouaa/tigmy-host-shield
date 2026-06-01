#!/bin/bash
# Setup free AI for guest ID verification (no OpenAI/Gemini quota needed)
set -e
cd "$(dirname "$0")/.."

echo "=== Option A: Local OCR (recommended, unlimited) ==="
echo "Install Tesseract (Ubuntu/Debian):"
echo "  sudo apt install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng"
echo ""
.venv/bin/pip install -q pytesseract 2>/dev/null || pip install pytesseract
echo "Add to .env:"
echo "  AI_PROVIDER=local"
echo ""

echo "=== Option B: Ollama (local vision model) ==="
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found. Pulling moondream (small vision model)..."
  ollama pull moondream || true
  echo "Add to .env:"
  echo "  AI_PROVIDER=ollama"
  echo "  OLLAMA_MODEL=moondream"
else
  echo "Install Ollama from https://ollama.com then re-run this script."
fi

echo ""
echo "Restart app: ./run.sh"
