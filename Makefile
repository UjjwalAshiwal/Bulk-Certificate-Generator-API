.PHONY: install dev test lint format migrate db-up db-down

install:
	pip install -e ".[test]"

dev:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

migrate:
	alembic upgrade head

db-up:
	docker compose up -d postgres

db-down:
	docker compose down
