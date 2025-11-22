
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment variables your app expects
ENV FLASK_ENV=production
ENV PORT=5010
ENV AUDIO_DIR=/data/recordings

# Expose the app port
EXPOSE 5000

CMD ["python", "run.py"]
