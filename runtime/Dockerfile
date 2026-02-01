# Runtime container for code execution
FROM python:3.14-slim

# Install system dependencies for code execution
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Create outputs directory for artifacts
RUN mkdir -p /workspace/outputs

# Keep container running (will be used for dynamic code execution)
CMD ["tail", "-f", "/dev/null"]
