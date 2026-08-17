FROM python:3.12-slim

ARG TESSERACT_LANGS="tesseract-ocr-eng tesseract-ocr-khm"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        ${TESSERACT_LANGS} \
        poppler-utils \
        libgl1 \
        libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python", "-m", "bot"]
