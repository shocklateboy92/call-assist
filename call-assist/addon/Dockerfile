FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for Matrix plugin
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

WORKDIR /app

# Copy proto files and generate Python bindings
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/*.proto

# Copy broker
COPY broker/ ./broker/
RUN pip install -r broker/requirements.txt

# Copy and build Matrix plugin
COPY plugins/matrix/ ./plugins/matrix/
WORKDIR /app/plugins/matrix
RUN npm install && npm run build

# Copy XMPP plugin (will be built separately)
WORKDIR /app
COPY plugins/xmpp/ ./plugins/xmpp/

# Expose gRPC port
EXPOSE 50051

# Start broker
CMD ["python", "-m", "broker.main"]