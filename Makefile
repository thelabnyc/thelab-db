docs_serve: docs_vendor
	DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.docgen_setup uv run zensical serve

docs_build: docs_vendor
	DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.docgen_setup uv run zensical build --strict
	uv run python bin/check-docs-csp.py build/mkdocs \
		--unused https://unpkg.com/ace-builds@ \
		--unused https://unpkg.com/pyodide@ \
		--unused https://cdn.jsdelivr.net/pyodide/ \
		--unused https://unpkg.com/resize-observer-polyfill \
		--unused https://unpkg.com/glightbox@ \
		--unused https://unpkg.com/mermaid@

docs_vendor:
	uv run python bin/vendor-docs-assets.py

docs: docs_build
	rm -rf public/ && \
	mkdir -p public/ && \
	cp -r build/mkdocs/* public/
