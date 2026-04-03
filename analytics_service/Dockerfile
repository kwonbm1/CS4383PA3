# Build from repo root: docker build -f analytics_service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fbschemas/ fbschemas/
COPY analytics_service/ analytics_service/

ENV PYTHONPATH=/app:/app/proto
CMD ["python", "-m", "analytics_service.subscriber"]
