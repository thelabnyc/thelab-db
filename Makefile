docs_serve:
	poetry run mkdocs serve --strict

docs_build:
	poetry run mkdocs build --strict

docs: docs_build
	rm -rf public/ && \
	mkdir -p public/ && \
	cp -r build/mkdocs/* public/
