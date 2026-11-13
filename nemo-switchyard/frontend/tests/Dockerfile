FROM mcr.microsoft.com/playwright/python:v1.58.0-noble
RUN pip install --no-cache-dir playwright==1.58.0
COPY browser.py /tests/browser.py
ENV QA_OUTPUT=/tmp/qa
CMD ["python", "/tests/browser.py"]
