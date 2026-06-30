FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY bot/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY bot/ ./bot/

# Data directory will be mounted as a Railway volume at /app/data
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

CMD ["python", "bot/main.py"]
