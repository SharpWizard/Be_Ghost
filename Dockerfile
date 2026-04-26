FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

COPY requirements.txt setup.py README.md ./
COPY be_ghost ./be_ghost

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# default: print fetched HTML to stdout
ENTRYPOINT ["be_ghost"]
CMD ["--help"]
