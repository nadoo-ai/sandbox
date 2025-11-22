# Contributing to Nadoo Sandbox

Thank you for your interest in contributing to Nadoo Sandbox! This document provides guidelines for contributing to this secure code execution service.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Docker Development](#docker-development)

## Code of Conduct

By participating in this project, you agree to be respectful and constructive in all interactions with the community.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up your development environment
4. Create a new branch for your changes
5. Make your changes
6. Test your changes
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- Redis (for local development)
- Poetry (recommended) or pip

### Setup with Poetry (Recommended)

```bash
# Install Poetry if you haven't
curl -sSL https://install.python-poetry.org | python3 -

# Clone your fork
git clone https://github.com/YOUR_USERNAME/sandbox.git
cd sandbox

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Setup with pip

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/sandbox.git
cd sandbox

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -e ".[dev]"
```

### Setup with Docker Compose (Recommended for Testing)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f sandbox

# Stop services
docker-compose down
```

### Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# At minimum, set:
# - NADOO_SANDBOX_API_KEY
# - NADOO_SANDBOX_SECRET_KEY
```

### Verify Installation

```bash
# Run the service
poetry run python -m src.main

# In another terminal, test the API
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"code": "print(\"Hello, World!\")", "language": "python"}'
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-language-support` - for new features
- `fix/memory-leak-issue` - for bug fixes
- `docs/update-api-reference` - for documentation
- `test/add-integration-tests` - for tests
- `refactor/simplify-docker-manager` - for refactoring

### Commit Messages

Follow conventional commits:
```
feat: add WebAssembly execution support
fix: resolve container cleanup race condition
docs: update API documentation for async endpoints
test: add integration tests for batch execution
refactor: simplify Docker container lifecycle
chore: update dependencies
```

## Code Style

We use automated tools to maintain code quality:

### Formatting with Black

```bash
# Format code (line length 100)
poetry run black src/

# Check formatting
poetry run black --check src/
```

### Import Sorting with isort

```bash
# Sort imports
poetry run isort src/

# Check import order
poetry run isort --check-only src/
```

### Linting with Flake8

```bash
# Run linter
poetry run flake8 src/
```

### Type Checking with mypy

```bash
# Type check
poetry run mypy src/
```

### Run All Checks

```bash
# Run all quality checks at once
poetry run black --check src/ && \
poetry run isort --check-only src/ && \
poetry run flake8 src/ && \
poetry run mypy src/
```

## Testing

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test file
poetry run pytest tests/test_execution_service.py

# Run specific test
poetry run pytest tests/test_execution_service.py::test_python_execution

# Run with verbose output
poetry run pytest -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names
- Aim for high coverage of new code

Example:
```python
import pytest
from src.services.execution_service import ExecutionService

@pytest.mark.asyncio
async def test_python_code_execution():
    """Test that Python code executes correctly"""
    service = ExecutionService()
    result = await service.execute_code(
        code='print("Hello, World!")',
        language="python"
    )

    assert result["success"] is True
    assert "Hello, World!" in result["output"]
```

### Integration Testing

```bash
# Test with Docker Compose
docker-compose up -d
./scripts/test_plugin_execution.sh
docker-compose down
```

### Manual API Testing

```bash
# Using curl
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "console.log(\"Hello from JS\");",
    "language": "javascript"
  }'

# Using httpie (if installed)
http POST http://localhost:8002/api/v1/execute \
  X-API-Key:your-api-key \
  code="print('Hello from Python')" \
  language=python
```

## Submitting Changes

### Pull Request Process

1. **Update your branch**
   ```bash
   git checkout main
   git pull upstream main
   git checkout your-branch
   git rebase main
   ```

2. **Run all checks**
   ```bash
   poetry run black src/
   poetry run isort src/
   poetry run flake8 src/
   poetry run mypy src/
   poetry run pytest
   ```

3. **Test Docker build**
   ```bash
   docker build -t nadoo-sandbox:test .
   docker build -f Dockerfile.plugin-runner -t nadoo-plugin-runner:test .
   ```

4. **Push to your fork**
   ```bash
   git push origin your-branch
   ```

5. **Create Pull Request**
   - Go to GitHub and create a PR
   - Fill out the PR template
   - Link any related issues

### PR Requirements

- ✅ All tests pass
- ✅ Code is formatted (Black, isort)
- ✅ No linting errors (Flake8)
- ✅ Type checks pass (mypy)
- ✅ New code has tests
- ✅ Documentation is updated
- ✅ CHANGELOG.md is updated (for significant changes)
- ✅ Docker images build successfully

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] New language support
- [ ] Performance improvement
- [ ] Security fix

## Related Issues
Fixes #123

## Testing
How was this tested?

## Docker Testing
- [ ] Docker image builds successfully
- [ ] docker-compose up works
- [ ] Test script passes

## Checklist
- [ ] Tests pass
- [ ] Code formatted (Black, isort)
- [ ] No lint errors (Flake8)
- [ ] Type checks pass (mypy)
- [ ] Documentation updated
- [ ] CHANGELOG updated
- [ ] Docker images tested
```

## Docker Development

### Building Images

```bash
# Build main service image
docker build -t nadoo-sandbox:dev .

# Build plugin runner image
docker build -f Dockerfile.plugin-runner -t nadoo-plugin-runner:dev .
```

### Testing Docker Images

```bash
# Run main service
docker run -d \
  --name nadoo-sandbox-test \
  -p 8002:8002 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e NADOO_SANDBOX_API_KEY=test-key \
  nadoo-sandbox:dev

# Test it
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"code": "print(42)", "language": "python"}'

# Clean up
docker rm -f nadoo-sandbox-test
```

### Debugging Containers

```bash
# View logs
docker logs nadoo-sandbox

# Execute shell in running container
docker exec -it nadoo-sandbox /bin/bash

# Inspect container
docker inspect nadoo-sandbox

# Check resource usage
docker stats nadoo-sandbox
```

## Adding Language Support

To add support for a new programming language:

1. **Add language configuration** in `src/core/config.py`
2. **Create Docker image** for the language
3. **Implement execution logic** in `src/core/docker_manager.py`
4. **Add tests** in `tests/test_languages.py`
5. **Update documentation** in README.md
6. **Update CHANGELOG.md**

Example:
```python
# In src/core/config.py
SUPPORTED_LANGUAGES = {
    # ... existing languages ...
    "julia": {
        "image": "julia:1.9-alpine",
        "file_extension": ".jl",
        "command": ["julia", "{file}"]
    }
}
```

## Security Considerations

When contributing, please keep in mind:

- **Never** execute untrusted code outside of isolated containers
- **Always** validate and sanitize user inputs
- **Use** resource limits for all executions
- **Enforce** network isolation for containers
- **Review** security implications of new features
- **Test** for common security vulnerabilities

See [SECURITY.md](./SECURITY.md) for detailed security guidelines.

## Questions?

- **GitHub Discussions**: https://github.com/nadoo-ai/sandbox/discussions
- **Issue Tracker**: https://github.com/nadoo-ai/sandbox/issues
- **Email**: dev@nadoo.ai

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing! 🎉
