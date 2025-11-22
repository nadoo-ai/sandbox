# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of Nadoo Sandbox seriously. Since this service executes untrusted code, security is our highest priority.

### Please DO NOT:

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before we have released a fix
- Exploit the vulnerability beyond what is necessary to demonstrate it
- Attempt to access or modify data belonging to other users
- Perform DoS attacks against the service

### Please DO:

1. **Email us directly** at **security@nadoo.ai**
2. Include a detailed description of the vulnerability
3. Provide steps to reproduce the issue
4. Include any proof-of-concept code (if applicable)
5. Suggest a fix or mitigation (if you have one)

### What to Include in Your Report

A good security report should include:

- **Description**: What is the vulnerability?
- **Impact**: What can an attacker do with this vulnerability?
- **Affected Components**: Docker manager, API, specific language executor, etc.
- **Severity**: How severe is this issue? (Critical, High, Medium, Low)
- **Reproduction Steps**: How to reproduce the vulnerability?
- **Proof of Concept**: Code demonstrating the issue (optional but helpful)
- **Suggested Fix**: Your ideas for fixing it (optional)

Example:
```
Subject: [SECURITY] Container Escape Vulnerability

Component: Docker Manager
Severity: Critical

Description:
A malicious code submission can escape the Docker container
by exploiting a misconfiguration in volume mounts.

Impact:
An attacker could gain access to the host filesystem and
execute arbitrary commands on the host machine.

Reproduction Steps:
1. Submit code with path traversal: "../../../etc/passwd"
2. Execute code that reads the file
3. Observe host filesystem access

Suggested Fix:
Use read-only volumes and enforce strict path validation.
Add seccomp profile to restrict syscalls.
```

## Response Timeline

- **Initial Response**: Within 24 hours
- **Status Updates**: Every 48 hours
- **Resolution Timeline**: Depends on severity
  - Critical: 48 hours
  - High: 7 days
  - Medium: 14 days
  - Low: 30 days

## Disclosure Policy

Once we have a fix ready:

1. We will notify you
2. We will coordinate disclosure timing with you
3. We will release a security advisory
4. We will credit you in the advisory (unless you prefer to remain anonymous)
5. We will release a patched version

---

## Security Architecture

### Container Isolation

Each code execution runs in an isolated Docker container:

```
┌─────────────────────────────────┐
│   Nadoo Sandbox Service         │
├─────────────────────────────────┤
│  - API Layer (Authentication)   │
│  - Execution Manager            │
│  - Resource Monitors            │
└───────────┬─────────────────────┘
            │
    ┌───────▼────────┐
    │ Docker Daemon  │
    └───────┬────────┘
            │
    ┌───────▼────────────────────────┐
    │  Isolated Container (per exec) │
    ├────────────────────────────────┤
    │  - User code execution         │
    │  - No network access           │
    │  - Resource limits enforced    │
    │  - Read-only filesystem        │
    │  - Restricted syscalls         │
    └────────────────────────────────┘
```

### Security Layers

1. **API Authentication**: API key required for all requests
2. **Input Validation**: All code and parameters validated
3. **Container Isolation**: Each execution in isolated container
4. **Resource Limits**: CPU, memory, time limits enforced
5. **Network Isolation**: No outbound network access
6. **Filesystem Isolation**: Read-only filesystem, no host access
7. **Syscall Filtering**: Restricted syscalls via seccomp

---

## Security Best Practices for Deployment

### 1. Docker Socket Access

**Critical**: The service requires access to Docker socket.

❌ **DANGEROUS**:
```bash
# Never give unrestricted socket access
docker run -v /var/run/docker.sock:/var/run/docker.sock nadoo-sandbox
```

✅ **SAFER**:
```bash
# Use Docker-in-Docker or rootless Docker
docker run --privileged nadoo-sandbox

# Or use socket proxy with access controls
# https://github.com/Tecnativa/docker-socket-proxy
```

### 2. API Key Management

```bash
# Generate strong API keys
openssl rand -hex 32

# Set in environment (never hardcode)
export NADOO_SANDBOX_API_KEY="your-secure-api-key-here"

# Rotate keys regularly
# Use different keys for different environments
```

### 3. Resource Limits

Configure appropriate limits in `.env`:

```bash
# Maximum execution time (seconds)
NADOO_SANDBOX_MAX_EXECUTION_TIME=30

# Maximum memory per container
NADOO_SANDBOX_MAX_MEMORY=512m

# Maximum CPU usage
NADOO_SANDBOX_MAX_CPU=0.5

# Maximum concurrent executions
NADOO_SANDBOX_MAX_CONCURRENT=10
```

### 4. Network Isolation

```bash
# Ensure containers have no network access
# This is enforced by default in code
# network_mode: "none"

# If network is needed, use strict firewall rules
# Only allow specific IPs/ports
```

### 5. Monitoring and Alerting

```bash
# Enable Prometheus metrics
NADOO_SANDBOX_METRICS_ENABLED=true

# Monitor for:
# - Execution failures
# - High resource usage
# - Container cleanup failures
# - API authentication failures

# Set up alerts for:
# - Multiple failed authentications
# - Container escape attempts
# - Resource limit violations
```

### 6. Secure Configuration

**Environment Variables**:
```bash
# Use strong secret keys
NADOO_SANDBOX_SECRET_KEY=$(openssl rand -hex 32)

# Disable debug in production
NADOO_SANDBOX_DEBUG=false

# Enable HTTPS
NADOO_SANDBOX_SSL_CERT=/path/to/cert.pem
NADOO_SANDBOX_SSL_KEY=/path/to/key.pem

# Configure rate limiting
NADOO_SANDBOX_RATE_LIMIT=100  # requests per minute
```

---

## Security Checklist for Operators

Before deploying to production:

- [ ] Docker socket access is restricted
- [ ] API keys are strong and rotated regularly
- [ ] HTTPS is enabled (TLS 1.2+)
- [ ] Resource limits are configured
- [ ] Network isolation is enforced
- [ ] Monitoring and alerting are set up
- [ ] Logs are collected and retained
- [ ] Regular security updates are applied
- [ ] Backups are configured
- [ ] Incident response plan is in place

---

## Known Security Considerations

### 1. Docker Socket Access

**Risk**: Service needs Docker socket access to create containers
**Mitigation**:
- Use rootless Docker when possible
- Use Docker socket proxy with access controls
- Run service in dedicated VM/host
- Monitor Docker API usage

### 2. Container Escape

**Risk**: Malicious code could attempt container escape
**Mitigation**:
- Use latest Docker version with security patches
- Enable seccomp profile
- Use AppArmor/SELinux profiles
- Run containers as non-root user
- Use read-only filesystems
- Disable capabilities

### 3. Resource Exhaustion

**Risk**: Malicious code could exhaust system resources
**Mitigation**:
- Enforce strict CPU limits
- Enforce strict memory limits
- Enforce execution timeouts
- Limit concurrent executions
- Monitor resource usage

### 4. Dependency Vulnerabilities

**Risk**: Dependencies may have security vulnerabilities
**Mitigation**:
- Regularly update dependencies
- Use `poetry update` or `pip-audit`
- Monitor security advisories
- Pin dependency versions

### 5. Data Leakage

**Risk**: Code could attempt to access sensitive data
**Mitigation**:
- No environment variables passed to containers
- No volume mounts to sensitive directories
- Network isolation prevents exfiltration
- Monitor for unusual patterns

---

## Security Features

### Implemented Protections

✅ **Container Isolation**
- Each execution in separate container
- Containers destroyed after execution
- No persistent state between executions

✅ **Resource Limits**
- CPU limits (default: 0.5 cores)
- Memory limits (default: 512MB)
- Execution timeouts (default: 30s)
- Concurrent execution limits

✅ **Network Isolation**
- No outbound network access by default
- No inbound connections
- DNS resolution disabled

✅ **Filesystem Restrictions**
- Read-only root filesystem
- Temporary directories only
- No access to host filesystem

✅ **API Security**
- API key authentication
- Rate limiting per key
- Input validation
- Request size limits

✅ **Monitoring**
- Prometheus metrics
- Execution audit logs
- Error tracking
- Performance monitoring

### Planned Enhancements

🔄 **Seccomp Profiles** (Coming Soon)
- Restrict syscalls available to containers
- Prevent privilege escalation attempts

🔄 **AppArmor/SELinux** (Coming Soon)
- Mandatory access control
- Additional kernel-level protection

🔄 **Image Scanning** (Coming Soon)
- Scan language images for vulnerabilities
- Automated security updates

🔄 **Audit Logging** (Coming Soon)
- Detailed audit trail
- Tamper-proof logging
- Log aggregation

---

## Incident Response

If you detect a security incident:

1. **Immediate Actions**:
   - Isolate affected systems
   - Disable compromised API keys
   - Stop affected containers
   - Preserve logs for analysis

2. **Notify Security Team**:
   - Email: security@nadoo.ai
   - Include: timestamp, affected systems, observed behavior

3. **Investigation**:
   - Review audit logs
   - Check container states
   - Analyze network traffic
   - Identify attack vector

4. **Recovery**:
   - Patch vulnerability
   - Rotate all API keys
   - Update Docker images
   - Restore from backups if needed

5. **Post-Incident**:
   - Document lessons learned
   - Update security measures
   - Notify affected users
   - Update security documentation

---

## Security Audit History

- **2025-11-22**: Initial security review for v0.1.0 release
- Future audits will be documented here

---

## Contact

- **Security Email**: security@nadoo.ai
- **General Support**: support@nadoo.ai
- **GitHub Security Advisories**: https://github.com/nadoo-ai/sandbox/security/advisories

---

## Credits

We thank the security researchers who have responsibly disclosed vulnerabilities:

- (No vulnerabilities reported yet)

---

**Last Updated**: 2025-11-22
