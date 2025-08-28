up:
	docker compose up -d

down:
	docker compose down -v

init-db:
	python scripts/init_local_dbs.py

helm-test:
	helm lint kubernetes/helm

.PHONY: smoke
smoke:
	python scripts/smoke_e2e.py
