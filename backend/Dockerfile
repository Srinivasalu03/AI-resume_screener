FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by pdfplumber / Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data to a shared location accessible by all users
ENV NLTK_DATA=/usr/local/nltk_data
RUN python -c "import nltk; nltk.download('punkt', download_dir='/usr/local/nltk_data', quiet=True); nltk.download('stopwords', download_dir='/usr/local/nltk_data', quiet=True)"

# Copy application code
COPY . .

# Create uploads directory and non-root user
RUN mkdir -p uploads downloads && \
    addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
