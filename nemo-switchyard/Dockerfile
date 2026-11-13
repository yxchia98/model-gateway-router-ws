FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates socat \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY serve.py routes.toml ./
ENV PYTHONUNBUFFERED=1 HOME=/tmp
USER 1000:1000
EXPOSE 4000
ENTRYPOINT ["python", "/app/serve.py"]
