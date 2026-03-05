# Build from repo root: docker build -f robot_service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto/ proto/
COPY fbschemas/ fbschemas/
COPY robot_service/ robot_service/

ENV PYTHONPATH=/app
# No EXPOSE: robot initiates outbound only
CMD ["python", "-m", "robot_service.robot", "--aisle", "bread"]
