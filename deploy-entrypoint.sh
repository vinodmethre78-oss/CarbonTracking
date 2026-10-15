#!/bin/sh
set -eu
cd /app/backend

echo "Applying database migrations..."
flask --app app db upgrade

echo "Seeding sample data only if the database is empty..."
python seed.py

echo "Starting CarbonTrack with Gunicorn..."
exec gunicorn --workers 1 --threads 4 --timeout 120 --bind "0.0.0.0:${PORT:-10000}" app:app
