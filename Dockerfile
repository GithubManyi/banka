FROM python:3.10-slim

# Set environment variables
ENV DBUS_SESSION_BUS_ADDRESS=""
ENV DBUS_SYSTEM_BUS_ADDRESS=""
ENV PYTHONUNBUFFERED=1

# Chrome/Chromium configuration for headless container environment
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/
ENV DISPLAY=:99
ENV NO_SANDBOX=true
ENV DISABLE_DEV_SHM=true
ENV ENABLE_CRASH_REPORTER=false
ENV CRASH_PAD_ENABLED=false
ENV CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu --disable-software-rasterizer --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --no-default-browser-check --no-first-run --disable-default-apps --disable-features=TranslateUI --disable-ipc-flooding-protection --enable-features=NetworkService,NetworkServiceInProcess --headless --remote-debugging-port=9222 --disable-webgl --disable-accelerated-2d-canvas --disable-accelerated-mjpeg-decode --disable-accelerated-video-decode --disable-vulkan --disable-gl-drawing-for-tests"

# Install system dependencies
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

# Create chromium config to disable crash reporting and GPU
RUN mkdir -p /etc/chromium && \
    echo '{"enable_crash_reporter": false, "hardware_acceleration_mode": {"enabled": false}, "browser": {"enable_spellchecking": false}}' > /etc/chromium/master_preferences

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

# Start Xvfb and application with proper error handling
CMD Xvfb :99 -screen 0 1024x768x16 -ac 2>/dev/null & \
    sleep 2 && \
    python web_ui.py
