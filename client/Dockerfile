# Build from repo root: docker build -f client/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY client/ client/

ENV PYTHONPATH=/app
EXPOSE 8501
CMD ["streamlit", "run", "client/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
