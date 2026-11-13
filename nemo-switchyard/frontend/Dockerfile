FROM python:3.12-slim-bookworm
WORKDIR /app
COPY server.py ./
COPY static ./static
ENV PYTHONUNBUFFERED=1
USER 1000:1000
EXPOSE 8080
CMD ["python", "server.py"]
