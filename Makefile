.PHONY: help build up down logs test clean

help:
	@echo "Neurality Health Voice Agent"
	@echo ""
	@echo "Usage:"
	@echo "  make build   - Build Docker images"
	@echo "  make up      - Start services"
	@echo "  make down    - Stop services"
	@echo "  make logs    - View logs"
	@echo "  make test    - Run tests"
	@echo "  make clean   - Remove containers"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo ""
	@echo "Services started!"
	@echo "Backend: http://localhost:8000"
	@echo "Health:  http://localhost:8000/health"

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	PYTHONPATH=. pytest -v

clean:
	docker-compose down -v --rmi local
