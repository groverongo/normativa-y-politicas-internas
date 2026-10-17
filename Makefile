MODULES := ingesta nttbanca-n

.PHONY: help modules install test ingesta-install ingesta-test ingesta-ingest ingesta-api ingesta-trace ingesta-docker-build ingesta-docker-run

help:
	@echo "Monorepo root Makefile. Modules: $(MODULES)"
	@echo ""
	@echo "  make modules            List module directories"
	@echo "  make install            Run 'make install' in every module that has a Makefile"
	@echo "  make test               Run 'make test' in every module that has a Makefile"
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
	@echo "modules/nttbanca-n has no Makefile of its own yet; use its own README/docker-compose directly, e.g.:"
	@echo "  cd modules/nttbanca-n && pip install -r requirements.txt"

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
