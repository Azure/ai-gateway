PYTHON ?= python
AZ ?= az

EXTENSION_VERSION := $(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('src/ai-gateway/pyproject.toml', 'rb'))['project']['version'])")
EXTENSION_WHEEL := dist/ai_gateway-$(EXTENSION_VERSION)-py3-none-any.whl

.PHONY: install-extension
install-extension:
	@if $(AZ) extension show --name ai-gateway >/dev/null 2>&1; then \
		$(AZ) extension remove --name ai-gateway; \
	fi
	$(PYTHON) -m build --wheel --outdir dist src/ai-gateway
	$(AZ) extension add --source $(EXTENSION_WHEEL) --yes
