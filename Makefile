PY?=python

.PHONY: venv install lint test smoke smoke-aw

venv:
	$(PY) -m venv .venv

install:
	. .venv/Scripts/activate && pip install -U pip && pip install -r requirements.txt -r requirements_fx.txt || true

lint:
	. .venv/Scripts/activate && $(PY) -m py_compile `git ls-files '*.py'` || true

test:
	. .venv/Scripts/activate && pytest -q || true

smoke:
	. .venv/Scripts/activate && $(PY) tools/smoke_run.py || true

smoke-aw:
	. .venv/Scripts/activate && $(PY) tools/smoke_awareness.py --symbol BTC/USDT --exchange bybit --limit 300 || true
HELM_RELEASE ?= leantraderbot
HELM_NAMESPACE ?= leantrader
HELM_CHART ?= infra/helm/leantraderbot

.PHONY: helm-install helm-upgrade helm-uninstall

helm-install:
	@helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) -n $(HELM_NAMESPACE) --create-namespace

helm-upgrade:
	@helm upgrade $(HELM_RELEASE) $(HELM_CHART) -n $(HELM_NAMESPACE)

helm-uninstall:
	@helm uninstall $(HELM_RELEASE) -n $(HELM_NAMESPACE)

