# Thin wrapper over the build script. `python src/make.py` still works and
# still runs from anywhere; these are the memorable names for it.
#
# `check` is the structural scan of the built page, `verify` is rebuild-and-diff.
# The same two words mean the same two things in website-awm, website-rtg, and
# website-ams.

.PHONY: build check verify links wireframes app

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

# `app` copies the Sagitta editor into sagitta/app/, so this site serves it:
# the files the browser needs and nothing of the desktop shell. See
# scripts/app.py. SAGITTA is the checkout to copy from; override it if yours
# lives elsewhere:
#
#     make app SAGITTA=~/Workshop/sagitta
#
# The result is tracked in this repo, because that is what gets served.
SAGITTA ?= ../sagitta

app:
	python scripts/app.py $(SAGITTA)
