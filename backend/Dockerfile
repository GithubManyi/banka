FROM python:3.10-slim

# Install system dependencies including ffmpeg and emoji fonts
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromium \
    chromium-driver \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    fonts-dejavu \
    libnss3 \
    libxss1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Create font directories and ensure font cache is updated
RUN mkdir -p /usr/share/fonts/truetype/noto && \
    fc-cache -f -v

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p frames tmp_ffmpeg static/assets

# Set Python path
ENV PYTHONPATH=/app

# Set Chromium path for Railway
ENV CHROMIUM_PATH=/usr/bin/chromium

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:7860')" || exit 1

# Start Python application
CMD ["python", "web_ui.py"]
