FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Install LangGraph (specific version compatible with our code)
RUN pip install --no-cache-dir "langgraph==0.0.15"

# Copy application code
COPY . .

# Copy our static UI into the image
COPY frontend /app/frontend

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser
RUN chown -R appuser:appuser /app
USER appuser

# Set Python path
ENV PYTHONPATH=/app

# Default command
CMD ["python", "-m", "services.api.main"]