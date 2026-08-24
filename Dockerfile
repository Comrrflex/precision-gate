FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin precision

COPY . /app
RUN python -m pip install --upgrade pip && python -m pip install .

USER 10001:10001

ENTRYPOINT ["precision-gate"]
CMD ["--help"]
