#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
  PIP=.venv/bin/pip
else
  PYTHON=python
  PIP=pip
fi

"$PIP" install -r requirements.txt

mkdir -p data/storage/signatures data/storage/pdfs data/storage/id_documents data/storage/archive_exports

"$PYTHON" scripts/run_all_migrations.py
"$PYTHON" scripts/init_db.py
