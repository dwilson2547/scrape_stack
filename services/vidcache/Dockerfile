FROM python:3.11-slim

# ffmpeg is required by the videohash library for frame extraction
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY main.py .

EXPOSE 8020

CMD ["python", "main.py", "--config", "/config/config.yaml"]
