FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY meshdesk ./meshdesk

RUN apt-get update \
    && apt-get install -y --no-install-recommends bluez \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir .

EXPOSE 8765

ENTRYPOINT ["python", "-m", "meshdesk"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
