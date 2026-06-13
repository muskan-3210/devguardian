FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000
# Respect $PORT (Render/Cloud Run inject it); fall back to 8000 locally.
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request as u; u.urlopen('http://localhost:%s/health' % os.environ.get('PORT','8000'))"

# Seed-if-empty then launch (see entrypoint.sh) — keeps demo data on the mounted volume.
CMD ["./entrypoint.sh"]
