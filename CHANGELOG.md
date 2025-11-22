# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- WebAssembly (WASM) support
- GPU-accelerated execution
- Kubernetes deployment support
- Plugin marketplace integration
- Enhanced monitoring dashboards
- Multi-region deployment

## [0.1.0] - 2025-11-22

### Added
- Initial public release
- **Multi-language Support**: Execute code in 12+ languages
  - Python 3.11
  - JavaScript (Node.js 20)
  - TypeScript (with ts-node)
  - Java (OpenJDK 17)
  - Go 1.21
  - Rust 1.74
  - C++ (GCC 13)
  - C# (.NET 8.0)
  - Ruby
  - PHP
  - SQL (PostgreSQL 16)
  - Bash
- **Secure Execution Environment**
  - Docker container isolation
  - Resource limits (CPU, memory, execution time)
  - Network isolation
  - Read-only filesystems
- **RESTful API**
  - Synchronous execution endpoint
  - Asynchronous execution endpoint
  - Batch execution support
  - Execution status tracking
  - Language capabilities query
- **Authentication & Security**
  - API key authentication
  - Rate limiting per API key
  - Input validation
  - Secure secret management
- **Monitoring & Observability**
  - Prometheus metrics
  - Health check endpoint
  - OpenTelemetry instrumentation
  - PostHog analytics integration
- **Infrastructure**
  - Docker-based deployment
  - docker-compose for local development
  - Redis for caching and sessions
  - Celery for async task processing
- **Developer Experience**
  - Comprehensive API documentation
  - OpenAPI/Swagger UI integration
  - Example code snippets
  - Environment configuration templates
  - Test scripts for validation

### Features
- **Async Execution**: Submit code for background execution
- **Session Management**: Track executions by session ID
- **Resource Limits**: Configurable CPU, memory, and time limits
- **Multi-tenancy**: Isolated execution environments per API key
- **Metrics Export**: Prometheus-compatible metrics

### Infrastructure
- FastAPI web framework
- Docker SDK for container management
- Redis for state management
- Celery for task queuing
- Uvicorn ASGI server

### Security
- Container isolation with Docker
- Network isolation (no outbound connections by default)
- Resource quotas enforced
- Input sanitization
- API key rotation support

### Documentation
- Comprehensive README with architecture diagrams
- API endpoint examples
- Configuration guide
- Docker deployment guide
- Troubleshooting section
- Language-specific notes

---

## Version Naming Convention

- **Major (X.0.0)**: Breaking API changes
- **Minor (0.X.0)**: New features, backward compatible
- **Patch (0.0.X)**: Bug fixes, backward compatible

## Release Process

1. Update CHANGELOG.md with version and date
2. Update version in pyproject.toml
3. Run full test suite: `pytest`
4. Run code quality checks:
   ```bash
   black --check src/
   isort --check-only src/
   flake8 src/
   mypy src/
   ```
5. Build Docker images:
   ```bash
   docker build -t nadoo-sandbox:vX.Y.Z .
   docker build -f Dockerfile.plugin-runner -t nadoo-plugin-runner:vX.Y.Z .
   ```
6. Test Docker deployment:
   ```bash
   docker-compose up -d
   ./test_plugin_execution.sh
   ```
7. Create git tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
8. Push tag: `git push origin vX.Y.Z`
9. Create GitHub Release with Docker images
10. Update documentation

---

[Unreleased]: https://github.com/nadoo-ai/sandbox/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nadoo-ai/sandbox/releases/tag/v0.1.0
