.PHONY: test test-privacy lint up down migrate seed smoke-local eval-build eval-oracle eval-calibrate eval-train-frozen eval-static eval-privacy eval-all eval-smoke retention

DATASET ?= synthetic-smoke
EXECUTOR ?= sim
SCALE ?= 0.3

test:
	python -m pytest

test-privacy:
	python -m eval.privacy_suite && python -m pytest backend/tests/test_privacy.py backend/tests/test_phase5_api.py -q

lint:
	python -m ruff check backend scripts eval

up:
	docker compose up --build

down:
	docker compose down

migrate:
	python -m alembic upgrade head

seed:
	python scripts/seed_demo.py

smoke-local:
	python scripts/profile_local.py --model $(MODEL)

retention:
	python scripts/retention.py

# ---- evaluation pipeline (docs/06). EXECUTOR=sim is a pipeline check, not a result. ----
eval-build:
	python -m eval.build_dataset --name $(DATASET) --scale $(SCALE)

eval-oracle:
	python -m eval.oracle --dataset $(DATASET) --executor $(EXECUTOR)

eval-calibrate:
	python -m eval.calibrate --dataset $(DATASET)

eval-train-frozen:
	python -m eval.train_frozen --dataset $(DATASET)

eval-static:
	python -m eval.run_baselines --dataset $(DATASET) --executor $(EXECUTOR)

eval-privacy:
	python -m eval.privacy_eval --dataset $(DATASET)

eval-all:
	python -m eval.run_all --dataset $(DATASET) --executor $(EXECUTOR) --scale $(SCALE)

# 10-item slice through every baseline, end to end, on the simulated executor
eval-smoke:
	python -m eval.build_dataset --name smoke-10 --scale 0.05
	python -m eval.oracle --dataset smoke-10 --limit 10
	python -m eval.train_frozen --dataset smoke-10
	python -m eval.run_baselines --dataset smoke-10 --limit 10 --seeds 0 --cold
