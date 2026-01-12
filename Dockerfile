FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for LiveKit
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgstreamer1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Download required model files for turn detection
RUN python agent.py download-files

# Default: run the agent
# Use SERVICE=backend to run the FastAPI server instead
ENV SERVICE=agent

CMD ["sh", "-c", "if [ \"$SERVICE\" = 'backend' ]; then uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}; else python agent.py start; fi"]
