FROM python:3.10-slim

# Install system dependencies including ffmpeg and Chromium for Selenium
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromium \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p frames tmp_ffmpeg static/assets

# Expose port
EXPOSE 7860

# Start Python application (NOT npm start)
CMD ["python", "web_ui.py"]
