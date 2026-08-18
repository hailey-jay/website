# Thin wrapper over the build script. `python src/make.py` still works and
# still runs from anywhere; these are the memorable names for it.
#
# `check` is the structural scan of the built page, `verify` is rebuild-and-diff.
# The same two words mean the same two things in website-awm, website-rtg, and
# website-ams.

.PHONY: build check verify links wireframes

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
