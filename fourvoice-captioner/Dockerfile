# FourVoice Captioner — AMD Hackathon ACT II Track 2
# Build: docker buildx build --platform linux/amd64 -t fourvoice-captioner:latest --load .
# Run:   docker run --rm --env-file .env -v ./sample_input:/input:ro -v ./sample_output:/output fourvoice-captioner:latest

FROM --platform=linux/amd64 python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fourvoice_captioner.py .

RUN mkdir -p /input /output

ENV INPUT_PATH=/input/tasks.json \
    INPUT_DIR=/input \
    OUTPUT_PATH=/output/results.json \
    OUTPUT_DIR=/output \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "fourvoice_captioner.py"]
CMD []
