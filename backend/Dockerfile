FROM amazon/aws-cli:2.36.26 AS awscli

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system gabflow && adduser --system --ingroup gabflow gabflow

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws

COPY . .
RUN mkdir -p /app/data/attachments /app/data/rag /models/whisper \
    && chmod +x /app/docker-entrypoint.sh \
    && chmod +x /app/migration-entrypoint.sh \
    && chmod +x /app/worker-entrypoint.sh \
    && chmod +x /app/parser-entrypoint.sh \
    && install -m 0755 /app/asm-exec /usr/local/bin/asm-exec \
    && chown -R gabflow:gabflow /app /models/whisper

EXPOSE 5000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
