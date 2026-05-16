# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Set Tesseract command for Linux environment
ENV TESSERACT_CMD=tesseract
# Set HuggingFace cache directory to a persistent location if possible
ENV HF_HOME=/app/cache/huggingface

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# libgl1 and libglib2.0-0 are required for OpenCV
# poppler-utils is required for pdf2image (PDF processing)
# tesseract-ocr and tesseract-ocr-vie for Vietnamese OCR support
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-vie \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Note: If deploying to a CPU-only environment, consider installing torch-cpu to save space
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories for data, database and cache
RUN mkdir -p data database database/images cache/huggingface

# Expose the port (Render/Railway usually provides PORT env var, default to 5000)
EXPOSE 5000

# Run the Flask API server
# We use --host 0.0.0.0 to make it accessible outside the container
CMD ["python", "main.py", "--api", "--port", "5000"]
