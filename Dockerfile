# -------------------------------
# Base image
# -------------------------------
FROM python:3.10-slim

# -------------------------------
# Install system dependencies
# -------------------------------
RUN apt-get update && apt-get install -y \
    ffmpeg \                       # Video processing
    chromium \                     # For headless browser / Selenium
    chromium-driver \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# Sanity check for FFmpeg
# -------------------------------
RUN ffmpeg -version   # Railway build logs will show this, ensures ffmpeg installed

# -------------------------------
# Set working directory
# -------------------------------
WORKDIR /app

# -------------------------------
# Install Python dependencies
# -------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -------------------------------
# Copy application code
# -------------------------------
COPY . .

# -------------------------------
# Create necessary directories
# -------------------------------
RUN mkdir -p frames tmp_ffmpeg static/assets

# -------------------------------
# Set Python path
# -------------------------------
ENV PYTHONPATH=/app

# -------------------------------
# Expose port for your web app
# -------------------------------
EXPOSE 7860

# -------------------------------
# Health check
# -------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:7860')" || exit 1

# -------------------------------
# Start Python application
# -------------------------------
CMD ["python", "web_ui.py"]
