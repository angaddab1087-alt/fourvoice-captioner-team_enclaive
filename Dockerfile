# Root Dockerfile — Backend (Express + Python)
FROM --platform=linux/amd64 node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY fourvoice-captioner/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Install Node deps
COPY fourvoice-captioner/package*.json ./
RUN npm install

# Copy source
COPY fourvoice-captioner/ .

# Ensure temp directories exist
RUN mkdir -p /input /output

ENV PORT=3001
EXPOSE 3001

# Start the Express server
CMD ["npm", "run", "dev:api"]
