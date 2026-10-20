# Thin wrapper over the build script. `python src/make.py` still works and
# still runs from anywhere; these are the memorable names for it.
#
# `check` is the structural scan of the built page, `verify` is rebuild-and-diff.
# The same two words mean the same two things in website-awm, website-rtg, and
# website-ams.

.PHONY: build check verify links wireframes app serve

build:
	python src/make.py

check:
	python scripts/check.py

verify:
	python scripts/verify.py

links:
	python scripts/check.py --links

wireframes:
	python scripts/gen_wireframes.py

# `serve` hosts the repo at http://localhost:$(PORT)/ to look at the built
# pages. It serves what is on disk, so run `make build` first. localhost
# counts as a secure context, so the browser editor's file access works here
# as it does over HTTPS. Override the port with `make serve PORT=9000`.
PORT ?= 8000

serve:
	python -m http.server $(PORT) --bind 127.0.0.1

# `app` copies the Sagitta editor into sagitta/app/, so this site serves it:
# the files the browser needs and nothing of the desktop shell. It clones
# SAGITTA_REF of SAGITTA fresh into a temporary directory every time, so
# whatever branch a working copy is on never leaks in. See scripts/app.py.
# They default to the public repo and its main branch; override either, e.g.
# to serve a release tag:
#
#     make app SAGITTA_REF=v0.6.0
#
# The result is tracked in this repo, because that is what gets served.
# `make check` reports when it is behind upstream's newest release.
SAGITTA ?=
SAGITTA_REF ?=

app:
	python scripts/app.py "$(SAGITTA)" "$(SAGITTA_REF)"
