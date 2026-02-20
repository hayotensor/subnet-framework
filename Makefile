.PHONY: setup run-app run-engine test lint clean

setup:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -e shared
	./.venv/bin/pip install -e app
	./.venv/bin/pip install -e engine
	./.venv/bin/pip install ruff pytest pytest-asyncio httpx

run-app:
	./.venv/bin/python -m app.server

run-engine:
	./.venv/bin/python -m engine.client

test:
	./.venv/bin/python -m pytest tests/ -v

lint:
	./.venv/bin/ruff check .
	./.venv/bin/ruff format --check .

clean:
	rm -rf .venv
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
