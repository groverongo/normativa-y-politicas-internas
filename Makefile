MODULES := ingesta nttbanca-n

.PHONY: help modules install test migrate migrate-status migrate-dry-run ingesta-install ingesta-test ingesta-ingest ingesta-api ingesta-trace ingesta-docker-build ingesta-docker-run

help:
	@echo "Monorepo root Makefile. Modules: $(MODULES)"
	@echo ""
	@echo "  make modules            List module directories"
	@echo "  make install            Run 'make install' in every module that has a Makefile"
	@echo "  make test               Run 'make test' in every module that has a Makefile"
	@echo ""
	@echo "Database (one shared migration sequence for both modules -- see modules/nttbanca-n/migrations/README.md):"
	@echo "  make migrate            Apply pending migrations"
	@echo "  make migrate-status     Show applied vs. pending migrations"
	@echo "  make migrate-dry-run    Apply + roll back all migrations, to validate a new one"
	@echo ""
	@echo "ingesta module shortcuts (see modules/ingesta/Makefile for the full list):"
	@echo "  make ingesta-install"
	@echo "  make ingesta-test"
	@echo "  make ingesta-ingest"
	@echo "  make ingesta-api"
	@echo "  make ingesta-trace FILE=<path>"
	@echo "  make ingesta-docker-build"
	@echo "  make ingesta-docker-run"
	@echo ""
	@echo "nttbanca-n module shortcuts (see modules/nttbanca-n/Makefile for the full list):"
	@echo "  make -C modules/nttbanca-n install"
	@echo "  make -C modules/nttbanca-n test"

modules:
	@for m in $(MODULES); do echo modules/$$m; done

install:
	@for m in $(MODULES); do \
		if [ -f modules/$$m/Makefile ]; then \
			echo "== make -C modules/$$m install =="; \
			$(MAKE) -C modules/$$m install; \
		fi; \
	done

test:
	@for m in $(MODULES); do \
		if [ -f modules/$$m/Makefile ]; then \
			echo "== make -C modules/$$m test =="; \
			$(MAKE) -C modules/$$m test; \
		fi; \
	done

migrate:
	$(MAKE) -C modules/nttbanca-n migrate

migrate-status:
	$(MAKE) -C modules/nttbanca-n migrate-status

migrate-dry-run:
	$(MAKE) -C modules/nttbanca-n migrate-dry-run

ingesta-install:
	$(MAKE) -C modules/ingesta install

ingesta-test:
	$(MAKE) -C modules/ingesta test

ingesta-ingest:
	$(MAKE) -C modules/ingesta ingest

ingesta-api:
	$(MAKE) -C modules/ingesta api

ingesta-trace:
	$(MAKE) -C modules/ingesta trace FILE=$(FILE)

ingesta-docker-build:
	$(MAKE) -C modules/ingesta docker-build

ingesta-docker-run:
	$(MAKE) -C modules/ingesta docker-run
