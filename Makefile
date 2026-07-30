.PHONY: install test run demo-key backup docker
install:
	python -m pip install -e '.[dev]'
test:
	pytest
run:
	PLO_DEMO_MODE=1 pallet-optimizer --data-dir data serve --host 127.0.0.1 --port 8000
demo-key:
	pallet-optimizer --data-dir data issue-api-key demo --label local
backup:
	pallet-optimizer --data-dir data backup backups
docker:
	docker compose up --build
