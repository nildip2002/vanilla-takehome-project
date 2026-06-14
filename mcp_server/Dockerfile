FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# In docker, we can expose it via SSE if we use FastMCP's SSE server mode,
# or we can just use stdio if the backend runs it as a subprocess.
# Wait, if MCP server is in a separate container, it needs to be HTTP/SSE.
# FastMCP allows starting an SSE server using `mcp.run(transport='sse')`.
# The PDF says: "The Agent Controller, acting in the capacity of the MCP Client, initializes a ClientSession over the standard input/output transport layer... spawns the MCP Server as a direct subprocess" AND "Tool servers can be detached from the stdio subprocess pattern and deployed as independent ECS tasks communicating via the streamable HTTP transport".
# Let's support running it via python. If the backend spawns it, the backend needs the mcp_server python files in its own container, or the MCP server runs as a separate container with SSE.
# To keep it simple and follow the "Local Architecture Diagram" ("FastMCP Client via Stdio"), the backend will run it as a subprocess.
# So we actually just need the MCP server files available to the backend, OR we can provide a Dockerfile in case we want to run it via SSE.
CMD ["python", "mcp_server.py"]
