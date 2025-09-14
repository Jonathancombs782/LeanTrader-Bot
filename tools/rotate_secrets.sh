#!/usr/bin/env bash
set -euo pipefail

# Template script for rotating secrets across targets.
#
# This script does NOT make changes unless --apply is provided. It prints the
# sequence of operations so operators can review first.
#
# Usage:
#   ./tools/rotate_secrets.sh --secret IBM_QUANTUM_API_KEY --value NEW_VALUE [--apply]
#   ./tools/rotate_secrets.sh --secret SLACK_WEBHOOK_URL --value https://hooks.slack.com/... [--apply]
#
# Optional flags:
#   --github       Update GitHub Actions secret (requires gh CLI configured)
#   --k8s          Update Kubernetes secret (kubectl context must be set)
#   --k8s-name     Secret name (default: leantraderbot-secrets)
#   --k8s-namespace Namespace (default: default)
#   --aws-sm       Update AWS Secrets Manager (requires aws CLI configured)
#   --gcp-sm       Update GCP Secret Manager (requires gcloud configured)
#

APPLY=0
GITHUB=0
K8S=0
AWS_SM=0
GCP_SM=0
K8S_NAME="leantraderbot-secrets"
K8S_NS="default"
SECRET=""
VALUE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift;;
    --github) GITHUB=1; shift;;
    --k8s) K8S=1; shift;;
    --k8s-name) K8S_NAME="$2"; shift 2;;
    --k8s-namespace) K8S_NS="$2"; shift 2;;
    --aws-sm) AWS_SM=1; shift;;
    --gcp-sm) GCP_SM=1; shift;;
    --secret) SECRET="$2"; shift 2;;
    --value) VALUE="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

if [[ -z "$SECRET" || -z "$VALUE" ]]; then
  echo "Usage: $0 --secret NAME --value VALUE [--apply] [--github|--k8s|--aws-sm|--gcp-sm]"
  exit 2
fi

echo "[rotate] Secret=$SECRET (value length ${#VALUE})"
echo "[rotate] Targets: github=$GITHUB k8s=$K8S aws_sm=$AWS_SM gcp_sm=$GCP_SM apply=$APPLY"

if [[ $GITHUB -eq 1 ]]; then
  echo "[rotate] GitHub Actions secret update: $SECRET"
  if [[ $APPLY -eq 1 ]]; then
    if command -v gh >/dev/null 2>&1; then
      gh secret set "$SECRET" --body "$VALUE"
    else
      echo "[rotate] gh CLI not installed; aborting GitHub secret update"; exit 1
    fi
  fi
fi

if [[ $K8S -eq 1 ]]; then
  echo "[rotate] Kubernetes secret update: name=$K8S_NAME ns=$K8S_NS key=$SECRET"
  if [[ $APPLY -eq 1 ]]; then
    if command -v kubectl >/dev/null 2>&1; then
      kubectl create secret generic "$K8S_NAME" -n "$K8S_NS" \
        --from-literal="$SECRET=$VALUE" \
        --dry-run=client -o yaml | kubectl apply -f -
    else
      echo "[rotate] kubectl not installed; aborting k8s secret update"; exit 1
    fi
  fi
fi

if [[ $AWS_SM -eq 1 ]]; then
  echo "[rotate] AWS Secrets Manager: key=$SECRET (update value)"
  echo "        Use: aws secretsmanager put-secret-value --secret-id <id> --secret-string '{\"$SECRET\":\"REDACTED\"}'"
  if [[ $APPLY -eq 1 ]]; then
    echo "[rotate] Implement provider-specific command here (template)."
  fi
fi

if [[ $GCP_SM -eq 1 ]]; then
  echo "[rotate] GCP Secret Manager: key=$SECRET (add new version)"
  echo "        Use: printf '%s' '$VALUE' | gcloud secrets versions add <secret-name> --data-file=-"
  if [[ $APPLY -eq 1 ]]; then
    echo "[rotate] Implement provider-specific command here (template)."
  fi
fi

echo "[rotate] Done. Review and verify consumers (CI, workloads) pick up the new secret."

