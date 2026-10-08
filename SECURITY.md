# IntelliVault AI Security

Production controls added: explicit CORS allowlist and headers, host validation, HSTS/security headers, JWT/Argon2 authentication, user-scoped database access, size/signature/page/chunk PDF limits, generated storage names, API/auth/upload rate limiting, non-root API/worker containers, private database/Redis ports, optional disabling of API docs and metrics, and safe production defaults.

## Deployment requirements
- Terminate TLS at a trusted reverse proxy/load balancer and redirect HTTP to HTTPS.
- Set a long random JWT secret through a managed secret store; rotate secrets and DB credentials.
- Set `TRUSTED_HOSTS` and `CORS_ORIGINS` to exact production hosts.
- Trust forwarded headers only from the actual proxy IPs. Never blindly trust arbitrary forwarding headers.
- Keep PostgreSQL, Redis, Ollama and Prometheus private.
- Put `/metrics` behind internal networking/authentication or keep `EXPOSE_METRICS=false`.
- Store PDFs in private object storage with encryption and retention rules for multi-host production.
- Add malware scanning/CDR before processing untrusted public uploads. Signature/size validation is not malware scanning.
- Use platform rate limiting/WAF for distributed deployments. The included in-process limiter is defense-in-depth, not a distributed global limiter.
- Run dependency/SAST/container scans in CI and keep base images/libraries patched.
- Back up PostgreSQL, test restores, and audit authorization failures without logging tokens, passwords, document text, or sensitive prompts.

## CI security scanning

The `Security` GitHub Actions workflow runs on pushes and pull requests to `main`, weekly, and manually. It includes:

- CodeQL SAST for Python and JavaScript/TypeScript using `security-extended` queries.
- Pull-request dependency review, failing on newly introduced high-or-critical vulnerabilities.
- `pip-audit` for Python dependency vulnerabilities.
- `npm audit` for high-or-critical frontend vulnerabilities.
- Trivy repository scanning for vulnerable dependencies, misconfiguration, IaC issues, and exposed secrets.
- Trivy scanning of the built API container image.
- SARIF uploads to GitHub code scanning where supported.
- Dependabot updates for pip, npm, and GitHub Actions.

### GitHub repository settings still required

1. Enable Code scanning / GitHub Code Security if your repository/plan requires it.
2. Enable Secret scanning and Push protection where available.
3. Enable Dependabot alerts and security updates.
4. Protect `main` and require the CI and Security jobs to pass before merge.
5. Restrict GitHub Actions permissions to read-only by default and allow write permission only to the security jobs that upload SARIF.
6. Never store production credentials in workflow YAML. Use GitHub Environments or repository/organization secrets.

For public repositories, CodeQL code scanning is available on GitHub.com. Availability for private repositories depends on the GitHub security product/plan enabled for the repository or organization.

## Upload malware scanning

Uploads are now streamed to a private ClamAV `clamd` service with the INSTREAM protocol before a document database record is created or a Celery parsing job is queued. In production the scanner fails closed by default: infected files are deleted and rejected; scanner errors delete the upload and return 503. The ClamAV service is not published on a host port. Signature data is persisted in the `clamav-data` volume.

ClamAV is one defense layer, not a guarantee against zero-days or malicious PDF parser exploits. Keep PDF libraries patched and consider content-disarm/reconstruction or sandboxing for high-risk Internet-facing deployments.
