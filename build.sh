#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Create static folder
mkdir -p static

# Collect static files
python manage.py collectstatic --no-input

# Run migrations (This creates the db.sqlite3 file on the server)
python manage.py migrate