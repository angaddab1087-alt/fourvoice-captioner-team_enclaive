# Root Dockerfile — delegates to fourvoice-captioner submission image
FROM --platform=linux/amd64 python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY fourvoice-captioner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fourvoice-captioner/fourvoice_captioner.py .
COPY fourvoice-captioner/scripts/ ./scripts/

RUN mkdir -p /input /output

ENV INPUT_PATH=/input/tasks.json \
    INPUT_DIR=/input \
    OUTPUT_PATH=/output/results.json \
    OUTPUT_DIR=/output \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "fourvoice_captioner.py"]
CMD []
