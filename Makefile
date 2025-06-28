docs_serve:
	DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.docgen_setup uv run mkdocs serve --strict

docs_build:
	DJANGO_SETTINGS_MODULE=thelabdb.tests.settings.docgen_setup uv run mkdocs build --strict

docs: docs_build
	rm -rf public/ && \
	mkdir -p public/ && \
	cp -r build/mkdocs/* public/
