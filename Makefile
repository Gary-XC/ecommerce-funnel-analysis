VENV=.venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

.PHONY: install install-dev fmt lint test dashboard clean

install:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e .

install-dev:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,dashboard]"

fmt:
	$(VENV)/bin/ruff format .

lint:
	$(VENV)/bin/ruff check .

test:
	$(VENV)/bin/pytest

dashboard:
	$(VENV)/bin/streamlit run dashboard/app.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete