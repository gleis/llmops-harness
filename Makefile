.PHONY: bootstrap teardown install dev up down test lint fmt eval smoke clean

bootstrap:
	bash scripts/bootstrap.sh

teardown:
	bash scripts/teardown.sh

install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

dev:
	. .venv/bin/activate && uvicorn llmops_harness.server:app --reload

up:
	docker compose -f deploy/docker-compose.yml up -d

down:
	docker compose -f deploy/docker-compose.yml down

test:
	. .venv/bin/activate && pytest -v

lint:
	. .venv/bin/activate && ruff check src tests

fmt:
	. .venv/bin/activate && ruff format src tests

eval:
	. .venv/bin/activate && python -m llmops_harness.evals --suite evals/suites/basic.yaml

smoke:
	bash scripts/smoke.sh

clean:
	rm -rf .venv build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
