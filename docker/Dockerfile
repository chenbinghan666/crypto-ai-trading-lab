FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LAB_BIND=0.0.0.0 LAB_STATE_DIR=/app/data/system LAB_LOG_DIR=/app/logs
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt /app/requirements.lock.txt
COPY requirements-freqai-cpu.lock.txt /app/requirements-freqai-cpu.lock.txt
RUN pip install --no-cache-dir --only-binary=:all: --no-binary=sdnotify -r requirements.lock.txt \
    && pip install --no-cache-dir --only-binary=:all: -c requirements.lock.txt -r requirements-freqai-cpu.lock.txt \
    && freqtrade install-ui --ui-version 3.1.3 \
    && useradd --create-home --uid 10001 lab
COPY --chown=lab:lab . /app
RUN mkdir -p /app/data/system /app/logs /app/user_data && chown -R lab:lab /app/data /app/logs /app/user_data
USER lab
EXPOSE 8080 8081
ENTRYPOINT ["python", "-m", "labapp.supervisor"]
