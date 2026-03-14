up:
	docker compose up -d

down:
	docker compose down -v

init-db:
	python scripts/init_local_dbs.py

db-migrate:
	alembic -c alembic.ini upgrade head

db-downgrade:
	alembic -c alembic.ini downgrade -1

db-revision:
	alembic -c alembic.ini revision --autogenerate -m "$(m)"

helm-test:
	helm lint kubernetes/helm

.PHONY: smoke db-migrate db-downgrade db-revision
smoke:
	python scripts/smoke_e2e.py
