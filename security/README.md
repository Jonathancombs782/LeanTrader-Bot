# Security, Secrets, and Crypto Posture

This document outlines how to handle secrets across environments and our current guidance for outbound cryptography, including a note on post‑quantum readiness.

## Secrets Management

Use the right mechanism for each environment. Never commit raw secrets to Git or Helm values.

- GitHub Actions (CI/CD):
  - Store credentials as encrypted repository or organization secrets.
  - Names used in this repo: `IBM_QUANTUM_API_KEY`, `Q_USE_RUNTIME`, `SLACK_WEBHOOK_URL`, etc.
  - Reference via `${{ secrets.NAME }}` in workflows. Rotate regularly (see below).

- Kubernetes (runtime):
  - Prefer Kubernetes Secrets created via your platform’s secret manager or an External Secrets operator:
    - AWS: AWS Secrets Manager + External Secrets Operator
    - GCP: Secret Manager + External Secrets Operator
    - Azure: Key Vault + CSI/ESO
  - For development only, the Helm chart can create an opaque Secret from `values.yaml` (`secrets.create: true`). Disable this in production and point to a pre‑created Secret (`secrets.create: false; secrets.name: <your-secret-name>`).

- Local development:
  - Use a local `.env` file (never commit it).
  - Restrict permissions (`chmod 600 .env`).
  - Populate only the values you need for an isolated dev run.

### Rotation Policy

- Rotate `IBM_QUANTUM_API_KEY` at least quarterly (or immediately on suspected exposure).
- Rotate Slack webhooks whenever personnel change or a workspace incident occurs.
- For cloud credentials (AWS/GCP/etc.), follow your org’s rotation SLAs (30–90 days typical).

A helper template is provided at `tools/rotate_secrets.sh` to remind operators of the sequence to rotate secrets across targets (GitHub, Kubernetes, and cloud secret stores). It is intentionally conservative and requires explicit confirmation to apply changes.

## Post‑Quantum Crypto (PQC) Note

- Track NIST PQC selections/finalists and their standardization status:
  - KEM: CRYSTALS‑Kyber (a.k.a. ML‑KEM)
  - Signatures: CRYSTALS‑Dilithium (a.k.a. ML‑DSA), Falcon, SPHINCS+
- Current guidance for client outbound connections:
  - Use TLS 1.3 everywhere; prefer modern cipher suites.
  - Maintain an upgrade path that can adopt PQC/TLS hybrids once they are broadly available in your stack and SDKs.
  - Libraries to watch for adoption in Python: `cryptography` (pyca), `libsodium`, vendor SDKs (IBM/Qiskit, cloud providers) as they roll out PQC support.
- For storage of secrets/configs, consider `sops` + KMS for defense‑in‑depth.

## Incident Handling (high level)

- If a secret is suspected to be exposed:
  1) Revoke/rotate the secret immediately in the upstream provider.
  2) Purge it from CI/CD and runtime Secret objects.
  3) Invalidate dependent sessions/keys where applicable.
  4) Document the incident and the remediation steps.

---

For questions about secure deployment or hardening, open an internal ticket and reference this README.

