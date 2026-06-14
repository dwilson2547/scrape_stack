FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY main.py .
COPY docker-config.yaml ./config.yaml

RUN mkdir -p /data/filecache /tmp/filecache

EXPOSE 8030

CMD ["python", "main.py", "--config", "config.yaml"]
