FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --uid 1001 --create-home --shell /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# OpenShift runs an arbitrary UID from the namespace range with GID 0; make /data group-writable.
RUN mkdir -p /data && chgrp -R 0 /data && chmod -R g=u /data

USER 1001

EXPOSE 8000

ENV DATABASE_URL=sqlite:////data/chat.db \
    HOST=0.0.0.0 \
    PORT=8000

CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST} --port ${PORT}"]
