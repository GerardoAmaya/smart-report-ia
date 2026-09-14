.PHONY: e2e e2e-up up down logs nuke migrate revision seed test lint fmt health tunnel webhook reports bench retention photos accuracy classifications grouping grouping-eval

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

e2e:           ## Pruebas extremo a extremo contra el sistema levantado
	@./scripts/e2e.sh $(args)

e2e-up:        ## Solo levanta el sistema con el Telegram falso
	@./scripts/e2e.sh --solo-levantar

lint:
	docker compose exec api ruff check .
	docker compose exec web npm run lint
	docker compose exec web npm run typecheck

fmt:
	docker compose exec api ruff format .
	docker compose exec api ruff check --fix .

health:
	@curl -s http://localhost:8000/health | python3 -m json.tool

bench:         ## Mide el costo por foto con 100 fotos calibradas
	docker compose exec api python -m benchmarks.storage_cost

accuracy:      ## Exactitud de clasificacion, con las confirmaciones del bot
	docker compose exec api python -m app.evaluation

classifications: ## Estado de la cola de clasificacion
	@docker compose exec -T db psql -U smart_report -d smart_report -c "\
	SELECT status, proposed_category, final_category, model, \
	       round(cost_usd, 6) AS usd, latency_ms FROM classifications \
	ORDER BY created_at DESC LIMIT 10;"

grouping:      ## Casos con sus reportes y la evidencia de cada union
	@docker compose exec -T db psql -U smart_report -d smart_report -c "\
	SELECT c.id, c.category, c.severity, c.status, c.report_count, \
	       round(ST_Y(c.centroid::geometry)::numeric,5) AS lat, \
	       round(ST_X(c.centroid::geometry)::numeric,5) AS lon \
	FROM cases c ORDER BY c.created_at DESC LIMIT 10;"
	@docker compose exec -T db psql -U smart_report -d smart_report -c "\
	SELECT decision, round(distance_m::numeric,1) AS metros, reason \
	FROM grouping_evidence ORDER BY created_at DESC LIMIT 10;"

grouping-eval: ## make grouping-eval f=verdad.json  — las dos tasas por separado
	docker compose exec api python -m app.grouping_eval $(f)

retention:     ## Aplica la politica de retencion. --dry-run para ver sin borrar.
	docker compose exec api python -m app.retention $(args)

photos:        ## Estado de la cola de fotos
	@docker compose exec -T db psql -U smart_report -d smart_report -c "\
	SELECT status, count(*), pg_size_pretty(sum(bytes)::bigint) AS bytes, \
	       sum(attempts) AS intentos \
	FROM report_photos GROUP BY status ORDER BY status;"

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
