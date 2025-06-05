FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install LangGraph
RUN pip install --no-cache-dir "langgraph==0.0.15"

# Copy project files
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set Python path to include the app directory
ENV PYTHONPATH=/app

# Get service to run from build arg (default to API service)
ARG SERVICE=api_service
ENV SERVICE_ENV=${SERVICE}

# Default command with dynamic service selection
CMD if [ "$SERVICE_ENV" = "api_service" ]; then \
        python -m services.api.main; \
    elif [ "$SERVICE_ENV" = "agent_service" ]; then \
        python -m services.agent_service.main; \
    elif [ "$SERVICE_ENV" = "agent_lifecycle" ]; then \
        python -m services.agent_lifecycle.main; \
    elif [ "$SERVICE_ENV" = "skill_service" ]; then \
        python -m services.skill_service.main; \
    else \
        python -m services.api.main; \
    fi

# Health check - the port will be determined by the service
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD if [ "$SERVICE_ENV" = "api_service" ]; then \
            curl -f http://localhost:8000/health || exit 1; \
        elif [ "$SERVICE_ENV" = "agent_service" ]; then \
            curl -f http://localhost:8003/health || exit 1; \
        elif [ "$SERVICE_ENV" = "agent_lifecycle" ]; then \
            curl -f http://localhost:8001/health || exit 1; \
        elif [ "$SERVICE_ENV" = "skill_service" ]; then \
            curl -f http://localhost:8002/health || exit 1; \
        else \
            curl -f http://localhost:8000/health || exit 1; \
        fi
