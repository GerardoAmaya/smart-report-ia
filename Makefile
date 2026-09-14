.PHONY: up down logs nuke migrate revision test lint fmt health

up:            ## Levanta base, API y frontend desde cero
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "API  http://localhost:8000/health"
	@echo "Web  http://localhost:3000"

down:
	docker compose down

nuke:          ## Borra tambien los datos
	docker compose down -v

logs:
	docker compose logs -f api web

migrate:
	docker compose exec api alembic upgrade head

revision:      ## make revision m="mensaje"
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:
	docker compose exec api pytest -q

lint:
	docker compose exec api ruff check .
	docker compose exec web npm run lint
	docker compose exec web npm run typecheck

fmt:
	docker compose exec api ruff format .
	docker compose exec api ruff check --fix .

health:
	@curl -s http://localhost:8000/health | python3 -m json.tool
