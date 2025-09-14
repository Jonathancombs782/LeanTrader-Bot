# LeanTraderBot Helm Chart

This chart deploys the LeanTraderBot API/metrics service with optional ingress and HPA.

Notes:
- The deployment expects the app to expose `/metrics` on port 8000 for liveness/readiness.
- Secrets in `values.yaml` under `secrets.stringData` are for development only.
  In production, create Kubernetes secrets separately and set `secrets.create=false` and
  `secrets.name=<your-secret-name>`.

Example (production) secret creation:

```
kubectl create secret generic leantraderbot-secrets \
  --from-literal=IBM_QUANTUM_API_KEY=... \
  --from-literal=SLACK_WEBHOOK_URL=... \
  --from-literal=REDIS_URL=... \
  --from-literal=Q_USE_RUNTIME=true \
  --from-literal=Q_ENABLE_QUANTUM=true
```

Then set in your `values.yaml` or via `--set`:

```
secrets:
  create: false
  name: leantraderbot-secrets
```

