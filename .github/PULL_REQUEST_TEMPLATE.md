## Description
Brief description of what this PR does.

## Type of Change
<!-- Mark the relevant option with an "x" -->

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code quality improvement (refactoring, type hints, etc.)
- [ ] Performance improvement
- [ ] Security fix
- [ ] New language support

## Related Issues
Fixes #(issue)

## Changes Made
<!-- List the specific changes made in this PR -->

-
-
-

## Testing

### Unit Tests
```bash
poetry run pytest
```

### Integration Tests
```bash
docker-compose up -d
./test_plugin_execution.sh
```

### Manual Testing
<!-- Describe any manual testing performed -->

API Request:
```bash
curl -X POST http://localhost:8002/api/v1/execute \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "language": "..."}'
```

Result:
```
Paste the response here
```

## Docker Testing
- [ ] Main service Docker image builds successfully
- [ ] Plugin runner Docker image builds successfully
- [ ] docker-compose up works
- [ ] Test script passes

## Code Quality
- [ ] Code follows style guide (Black, isort)
- [ ] No linting errors (Flake8)
- [ ] Type checks pass (mypy)
- [ ] All tests pass
- [ ] New code has tests
- [ ] Code coverage maintained or improved

## Documentation
- [ ] README updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] API documentation updated (if applicable)
- [ ] Code comments added for complex logic

## Security
- [ ] No secrets or API keys in code
- [ ] Input validation implemented
- [ ] Resource limits considered
- [ ] Security implications reviewed
- [ ] No new security vulnerabilities introduced

## Performance
- [ ] Performance implications considered
- [ ] Resource usage is reasonable
- [ ] No memory leaks
- [ ] Execution time is acceptable

## Breaking Changes
<!-- If this is a breaking change, describe what breaks and migration path -->

**What breaks:**
-

**Migration guide:**
```
Before:
...

After:
...
```

## Screenshots / Logs
<!-- If applicable, add screenshots or logs to help explain your changes -->

## Additional Notes
<!-- Add any other context about the PR here -->

---

## Checklist for Reviewers
- [ ] Code quality is good
- [ ] Tests are comprehensive
- [ ] Documentation is clear
- [ ] No security vulnerabilities
- [ ] Performance is acceptable
- [ ] Docker images build successfully
