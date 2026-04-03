# Build from repo root: docker build -f pricing_service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto/ proto/
COPY pricing_service/ pricing_service/

ENV PYTHONPATH=/app:/app/proto
EXPOSE 50052
CMD ["python", "-m", "pricing_service.server"]
