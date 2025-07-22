up:
	docker compose up -d

down:
	docker compose down -v

helm-test:
	helm lint kubernetes/helm
