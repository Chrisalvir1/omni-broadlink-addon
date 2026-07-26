ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python, dependencies, and network tools
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

# Install python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    broadlink \
    fastapi \
    uvicorn \
    pydantic \
    requests

# Copy application files
COPY src/ /app/src/
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

CMD [ "/app/run.sh" ]
