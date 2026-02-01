# Use Python 3.14 slim image
FROM python:3.14-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first
COPY pyproject.toml ./

# Copy application code (needed for -e install)
COPY . .

# Install Python dependencies
# Install in editable mode so code changes are reflected
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /app/data/artifacts

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
