.PHONY: build run stop logs test clean

build:
	docker-compose build

run:
	docker-compose up -d

stop:
	docker-compose down

logs:
	docker-compose logs -f telegram-bot

test:
	docker-compose run --rm telegram-bot python -m pytest tests/ -v

clean:
	docker-compose down -v
	docker system prune -f

setup:
	mkdir -p logs
	docker-compose build