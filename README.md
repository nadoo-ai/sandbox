# Nadoo Sandbox

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)
[![CI](https://github.com/nadoo-ai/sandbox/workflows/CI/badge.svg)](https://github.com/nadoo-ai/sandbox/actions)
[![codecov](https://codecov.io/gh/nadoo-ai/sandbox/branch/main/graph/badge.svg)](https://codecov.io/gh/nadoo-ai/sandbox)

**Secure code execution service for the Nadoo AI Platform.**

Execute code in 12+ programming languages within isolated Docker containers. Perfect for online code editors, automated testing, educational platforms, and AI-powered coding assistants.

---

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/nadoo-ai/sandbox.git
cd sandbox

# Copy environment file
cp .env.example .env
# Edit .env and set your API key

# Start services
docker-compose up -d

# Test the API
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"code": "print(\"Hello, Nadoo!\")", "language": "python"}'
```

Access the service:
- **API**: http://localhost:8002
- **Swagger UI**: http://localhost:8002/docs
- **Health Check**: http://localhost:8002/health
- **Metrics**: http://localhost:8002/metrics

### Using Python Directly

```bash
# Install dependencies
poetry install

# Set environment variables
export NADOO_SANDBOX_API_KEY="your-secure-api-key"
export NADOO_SANDBOX_REDIS_URL="redis://localhost:6379/2"

# Run the service
poetry run python -m src.main
```

---

## Features

- **Multi-language Support**: Execute code in Python, JavaScript, TypeScript, Java, Go, Rust, C++, C#, Ruby, PHP, SQL, and Bash
- **Secure Execution**: All code runs in isolated Docker containers with resource limits
- **Async Execution**: Support for both synchronous and asynchronous code execution
- **Rate Limiting**: Built-in rate limiting to prevent abuse
- **Session Management**: Track executions by session
- **Metrics & Monitoring**: Prometheus metrics and health checks

## Architecture

```
┌─────────────────┐
│   API Gateway   │
└────────┬────────┘
         │
┌────────▼────────┐
│  FastAPI App    │
├─────────────────┤
│ - Execute API   │
│ - Health Check  │
│ - Metrics       │
└────────┬────────┘
         │
┌────────▼────────┐
│ Docker Manager  │
├─────────────────┤
│ - Container     │
│   Creation      │
│ - Code Exec     │
│ - Cleanup       │
└────────┬────────┘
         │
┌────────▼────────┐
│ Docker Daemon   │
└─────────────────┘
```

## API Usage Examples

### Python

```bash
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "print(\"Hello, World!\")\nprint(2 + 2)",
    "language": "python"
  }'
```

### JavaScript

```bash
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "console.log(\"Hello from Node.js\");",
    "language": "javascript"
  }'
```

### With stdin

```bash
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "name = input(\"Enter your name: \")\nprint(f\"Hello, {name}!\")",
    "language": "python",
    "stdin": "Nadoo"
  }'
```

### With Custom Timeout

```bash
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "import time\ntime.sleep(5)\nprint(\"Done!\")",
    "language": "python",
    "timeout": 10
  }'
```

---

## API Endpoints

### Execute Code (Synchronous)
```http
POST /api/v1/execute
X-API-Key: your-api-key

{
  "code": "print('Hello, World!')",
  "language": "python",
  "stdin": "optional input",
  "environment": {
    "VAR": "value"
  },
  "timeout": 30
}

Response:
{
  "success": true,
  "output": "Hello, World!\n",
  "error": null,
  "execution_time": 0.123,
  "language": "python"
}
```

### Async Execution
```http
POST /api/v1/execute/async
X-API-Key: your-api-key

{
  "code": "console.log('Hello');",
  "language": "javascript"
}
```

### Get Execution Status
```http
GET /api/v1/execute/status/{execution_id}
X-API-Key: your-api-key
```

### Batch Execution
```http
POST /api/v1/execute/batch
X-API-Key: your-api-key

[
  {
    "code": "print('Python')",
    "language": "python"
  },
  {
    "code": "console.log('JS')",
    "language": "javascript"
  }
]
```

### Supported Languages
```http
GET /api/v1/execute/languages
```

## Configuration

Environment variables:

```bash
# Application
NADOO_SANDBOX_APP_NAME="Nadoo Sandbox Service"
NADOO_SANDBOX_DEBUG=false

# Server
NADOO_SANDBOX_HOST=0.0.0.0
NADOO_SANDBOX_PORT=8002

# Security
NADOO_SANDBOX_SECRET_KEY=your-secret-key
NADOO_SANDBOX_API_KEY=your-api-key

# Docker
NADOO_SANDBOX_DOCKER_SOCKET=unix://var/run/docker.sock
NADOO_SANDBOX_MAX_EXECUTION_TIME=60
NADOO_SANDBOX_MAX_MEMORY=512m
NADOO_SANDBOX_MAX_CPU=0.5

# Redis
NADOO_SANDBOX_REDIS_URL=redis://localhost:6379/2
```

## Development

### Setup
```bash
# Install dependencies
poetry install

# Run locally
poetry run python -m src.main
```

### Testing
```bash
# Run tests
poetry run pytest

# With coverage
poetry run pytest --cov=src

# Linting
poetry run black src/
poetry run isort src/
poetry run flake8 src/
poetry run mypy src/
```

## Docker Deployment

### Build Image
```bash
docker build -t nadoo-sandbox:latest .
```

### Run Container
```bash
docker run -d \
  --name nadoo-sandbox \
  -p 8002:8002 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e NADOO_SANDBOX_API_KEY=your-api-key \
  nadoo-sandbox:latest
```

## Security Considerations

1. **Container Isolation**: Each code execution runs in an isolated container
2. **Resource Limits**: CPU, memory, and execution time limits enforced
3. **Network Isolation**: Containers have no network access by default
4. **API Authentication**: All endpoints require API key authentication
5. **Rate Limiting**: Configurable rate limits per API key
6. **Input Validation**: All inputs are validated before execution

## Language-Specific Notes

### Python
- Uses Python 3.11 slim image
- Supports standard library and basic operations

### JavaScript/TypeScript
- Uses Node.js 20 slim image
- TypeScript compiled with ts-node

### Java
- Uses OpenJDK 17 slim image
- Compiles and runs single file programs

### Go
- Uses Go 1.21 Alpine image
- Runs with `go run`

### Rust
- Uses Rust 1.74 slim image
- Compiles with rustc

### C++
- Uses GCC 13 image
- Compiles with g++

### C#
- Uses .NET SDK 8.0 image
- Runs with dotnet script

### SQL
- Uses PostgreSQL 16 Alpine image
- Executes SQL statements

## Monitoring

### Prometheus Metrics
Available at `/metrics` endpoint:

- `sandbox_executions_total`: Total number of executions
- `sandbox_execution_duration_seconds`: Execution duration histogram
- `sandbox_active_containers`: Number of active containers
- `sandbox_errors_total`: Total number of errors

### Health Check
```http
GET /health
```

Returns service health status and component checks.

## Troubleshooting

### Container Cleanup
If containers are not cleaned up properly:

```bash
# List all sandbox containers
docker ps -a | grep nadoo-sandbox

# Force remove all sandbox containers
docker rm -f $(docker ps -a | grep nadoo-sandbox | awk '{print $1}')
```

### Docker Socket Permission
Ensure the service has access to Docker socket:

```bash
chmod 666 /var/run/docker.sock
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## Security

Security is our top priority. Please see [SECURITY.md](./SECURITY.md) for security guidelines and how to report vulnerabilities.

## License

MIT License - see [LICENSE](./LICENSE) file for details.

Copyright (c) 2025 Nadoo AI
