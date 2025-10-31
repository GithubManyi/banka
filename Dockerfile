FROM python:3.10-slim

# Set environment variables to disable D-Bus and suppress errors
ENV DBUS_SESSION_BUS_ADDRESS=""
ENV DBUS_SYSTEM_BUS_ADDRESS=""

# Chrome/Chromium specific environment variables
ENV CHROME_DRIVER=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium
ENV DISPLAY=:99
ENV NO_SANDBOX=true
ENV DISABLE_DEV_SHM=true
ENV ENABLE_CRASH_REPORTER=false
ENV CRASH_PAD_ENABLED=false

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
    xvfb \
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

# Start Xvfb and then your Python application
CMD Xvfb :99 -screen 0 1024x768x16 & python web_ui.py
