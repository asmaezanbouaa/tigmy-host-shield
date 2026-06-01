#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

pip install -r requirements.txt

mkdir -p data
mkdir -p storage/signatures storage/pdfs storage/id_documents storage/archive_exports

python scripts/migrate_v2.py 2>/dev/null || true
python scripts/init_db.py
