up:
	docker compose up -d

down:
	docker compose down -v

helm-test:
	helm lint kubernetes/helm

.PHONY: smoke
smoke:
	python scripts/smoke_e2e.py
