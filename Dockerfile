# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_FILE=/app/data/data.json \
    TUNNEL_STATE_FILE=/app/data/tunnels_state.json

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Copy the rest of the project
COPY . .

# Run as an unprivileged user with a writable data directory
RUN useradd -m -u 1000 -s /usr/sbin/nologin panel \
    && mkdir -p /app/data \
    && chown -R panel:panel /app/data
USER panel

EXPOSE 5000

# Command to run the application
CMD ["python3", "app.py"]
 