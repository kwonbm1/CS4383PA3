# Build from repo root: docker build -f inventory_service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto/ proto/
COPY fbschemas/ fbschemas/
COPY inventory_service/ inventory_service/

ENV PYTHONPATH=/app
EXPOSE 50051 5556
CMD ["python", "-m", "inventory_service.server"]
