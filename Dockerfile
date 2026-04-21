FROM python:3.11-slim

WORKDIR /app

# pymupdf needs a few runtime libs; mammoth is pure python.
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl libjpeg62-turbo libopenjp2-7 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
