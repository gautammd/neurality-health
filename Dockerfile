FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for LiveKit and supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgstreamer1.0-0 \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Download required model files for turn detection
RUN python agent.py download-files

# Default port for Railway
ENV PORT=8000

# Run both agent and backend via supervisord
CMD ["supervisord", "-c", "supervisord.conf"]
