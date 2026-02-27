FROM python:3.12-slim

# Install Azure CLI (needed for az acr build, az containerapp, az cosmosdb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg lsb-release ca-certificates && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8000

# Entrypoint: login to Azure with MI, then start MCP server
COPY entrypoint.sh .
COPY run_server.py .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
