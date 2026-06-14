FROM python:3.11-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install MCP server dependencies
COPY mcp_server/requirements.txt ./mcp_requirements.txt
RUN if [ -s ./mcp_requirements.txt ]; then pip install --no-cache-dir -r mcp_requirements.txt; fi

# Copy source code
COPY backend/ ./
COPY mcp_server/ ./mcp_server/

ENV MCP_SERVER_PATH=/app/mcp_server/mcp_server.py
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
