.PHONY: up down logs nuke migrate revision seed test lint fmt health tunnel webhook reports

up:            ## Levanta base, almacenamiento, API y frontend desde cero
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "API    http://localhost:8000/health"
	@echo "Web    http://localhost:3100"
	@echo "MinIO  http://localhost:9001"

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

seed:          ## Datos de siembra. Idempotente: se puede correr siempre.
	docker compose exec api python -m seeders.runner

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

tunnel:        ## Tunel HTTPS y registro del webhook. Ctrl-C para bajarlo.
	@./scripts/tunnel.sh

webhook:       ## Que dice Telegram del webhook ahora mismo
	@./scripts/webhook.sh

reports:       ## Ultimos reportes con sus coordenadas y fotos
	@docker compose exec -T db psql -U smart_report -d smart_report -c "\
	SELECT r.id, r.status, r.caption, \
	       round(ST_Y(r.location::geometry)::numeric, 5) AS lat, \
	       round(ST_X(r.location::geometry)::numeric, 5) AS lon, \
	       count(p.id) AS fotos, r.created_at \
	FROM reports r LEFT JOIN report_photos p ON p.report_id = r.id \
	GROUP BY r.id ORDER BY r.created_at DESC LIMIT 10;"
