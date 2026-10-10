ARG BUILD_FROM=alpine:3.19
FROM ${BUILD_FROM}

# Install Python, build tools, and network utilities required by Broadlink.
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    curl

# Create app directory
WORKDIR /app

# Install pinned runtime dependencies so rebuilds are reproducible.
COPY requirements.lock /app/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes -r /app/requirements.lock

# Copy application files
COPY src/ /app/src/
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

CMD [ "/app/run.sh" ]
