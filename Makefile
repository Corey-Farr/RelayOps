PYTHON ?= python

.PHONY: demo up down clean test lint smoke benchmark
demo:
	$(PYTHON) scripts/demo.py demo
up:
	$(PYTHON) scripts/demo.py up
down:
	$(PYTHON) scripts/demo.py down
clean:
	$(PYTHON) scripts/demo.py clean
test:
	cd backend && $(PYTHON) -m pytest
	$(PYTHON) -m unittest discover -s demo-sink -v
	cd frontend && npm run test
lint:
	cd backend && $(PYTHON) -m ruff check . && $(PYTHON) -m ruff format --check . && $(PYTHON) -m mypy relayops
	cd frontend && npm run lint && npm run typecheck
smoke:
	$(PYTHON) scripts/smoke.py --monitoring
benchmark:
	$(PYTHON) benchmarks/run.py
