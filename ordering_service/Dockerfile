# Build from repo root: docker build -f ordering_service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto/ proto/
COPY fbschemas/ fbschemas/
COPY ordering_service/ ordering_service/

ENV PYTHONPATH=/app
EXPOSE 5001 5557
CMD ["python", "-m", "ordering_service.app"]
