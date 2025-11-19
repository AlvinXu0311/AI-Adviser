FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal build deps (some python packages need compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the backend app
COPY . .

ENV REDIS_HOST=redis
ENV REDIS_PORT=6379

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
