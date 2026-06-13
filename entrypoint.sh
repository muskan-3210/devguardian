#!/bin/sh
# Seed the database on first start only — runs AFTER the data volume is mounted,
# so seeded data lands in the persistent volume (not a throwaway build layer).
set -e

: "${DATABASE_PATH:=devguardian.db}"

if [ ! -f "$DATABASE_PATH" ]; then
    echo "No database at $DATABASE_PATH — seeding demo data..."
    python -m app.seeder
else
    echo "Database found at $DATABASE_PATH — skipping seed."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
