FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
# psycopg/boto3 are commented out in requirements.txt (optional, only needed
# for STORAGE_BACKEND=postgres) but this image is meant to run the real
# S3/Postgres-backed storage, so install them explicitly.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "psycopg[binary]>=3.1" "boto3>=1.34"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
