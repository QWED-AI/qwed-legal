# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously at QWED.

### How to Report

**DO NOT** file a public GitHub issue for security vulnerabilities.

Instead, please report security vulnerabilities by emailing:

📧 **security@qwedai.com**

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

### Response Timeline

| Action | Timeline |
|--------|----------|
| Acknowledgment | Within 48 hours |
| Initial Assessment | Within 1 week |
| Fix Released | Depends on severity |

### Severity Levels

| Level | Description | Response |
|-------|-------------|----------|
| **Critical** | Remote code execution, data exfiltration | Immediate patch |
| **High** | Authentication bypass, privilege escalation | Fix within 7 days |
| **Medium** | Information disclosure | Fix within 30 days |
| **Low** | Minor issues | Next regular release |

## Security Features

QWED-Legal is designed with security in mind:

### What We Verify

- **No code execution**: We parse and verify, not execute
- **No network calls**: All verification is local
- **No file system access**: Contracts are passed as strings

### Dependencies

We use trusted, audited dependencies:

| Dependency | Purpose | Security Profile |
|------------|---------|------------------|
| z3-solver | Logic verification | Microsoft-backed |
| sympy | Math verification | Widely audited |
| python-dateutil | Date parsing | Mature library |
| holidays | Holiday calendars | Read-only data |

## Responsible Disclosure

We follow responsible disclosure practices:

1. **Report** vulnerability privately
2. **Investigate** and confirm the issue
3. **Fix** the vulnerability
4. **Release** patch publicly
5. **Credit** the reporter (if desired)

## Bug Bounty

Currently, we do not have a formal bug bounty program, but we deeply appreciate security researchers who help us improve.

Reporters of valid security issues will receive:
- Recognition in our SECURITY.md (if desired)
- A small token of appreciation

## Contact

- 📧 Email: security@qwedai.com
- 🔐 GPG Key: Available upon request
