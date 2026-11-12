FROM python:3.10-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn python-multipart

# Copy application files
COPY . .

EXPOSE 8000

CMD ["uvicorn", "web_app.server:app", "--host", "0.0.0.0", "--port", "8000"]
