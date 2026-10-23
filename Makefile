# Targets mirror `python -m ffsa.cli <target>` so Windows users without make can run the same steps.
PY ?= .venv/Scripts/python
ifeq ($(OS),)
PY = .venv/bin/python
endif
WORLD ?= toy

.PHONY: setup data test sim sweep export figures dash assumptions

setup:
	python -m venv .venv
	$(PY) -m pip install -e ".[dev,geo]"
	cd dashboard && npm install && node scripts/vendor.mjs

data:
	$(PY) -m ffsa.cli data

test:
	$(PY) -m pytest -q

sim:
	$(PY) -m ffsa.cli --allow-placeholders sim --world $(WORLD)

sweep:
	$(PY) -m ffsa.cli --allow-placeholders sweep --world $(WORLD) --jobs 2

export:
	$(PY) -m ffsa.cli export --world $(WORLD)

figures:
	$(PY) -m ffsa.cli figures

assumptions:
	$(PY) -m ffsa.cli assumptions

dash:
	$(PY) -m http.server 8000 --directory dashboard
