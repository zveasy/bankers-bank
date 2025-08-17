# Container Image Hygiene Runbook

## Goals
* Keep container images minimal, reproducible, and free from vulnerabilities.
* Ensure deterministic builds via pinned dependency versions.
* Automated scanning & cleanup of stale tags.

## Guidelines
1. **Base Images**
   * Use `python:3.11-slim` or `alpine` where feasible.
   * Pin to a specific SHA (e.g., `python@sha256:...`) in production to avoid drift.
2. **Package Installation**
   * Prefer wheels over source builds.
   * Clean apt/yum cache (`rm -rf /var/lib/apt/lists/*`).
   * Use multi-stage builds to drop build deps.
3. **User & Permissions**
   * Create non‐root user (`appuser`) and switch (`USER appuser`).
   * Ensure writable dirs (`/data`, `/var/log/app`) are owned by `appuser`.
4. **Vulnerability Scanning**
   * Trivy scan in CI on PRs.
   * Critical/High CVEs must be fixed before merge.
5. **Tag Strategy**
   * `:sha-<git>` immutable digest tag.
   * `:latest` only in dev/test.
   * Retain last 10 prod tags; prune older via registry TTL.
6. **SBOM**
   * Generate Software Bill of Materials via `cyclonedx-python` and attach as artifact.

## Incident Response
| Issue | Mitigation |
|-------|------------|
| New CVE in base image | Rebuild with patched base and redeploy. |
| Image size growth | Run `dive` to inspect layers; identify large additions. |
| Missing dependency | Rebuild with updated `requirements.lock`; ensure pin. |
