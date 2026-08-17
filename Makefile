# Thin wrapper over the build script. `python src/make.py` still works and
# still runs from anywhere; these are the memorable names for it.

.PHONY: build check wireframes

build:
	python src/make.py

# index.html and rss.xml are committed and served directly, so stale output
# ships silently. The build is deterministic (the feed's lastBuildDate comes
# from the newest post's date, not the clock), so a rebuild that leaves these
# two files unchanged means the committed output is current.
#
# images/thumbs/ is deliberately not checked: it regenerates on mtime, and a
# fresh checkout's mtimes are checkout time.
check: build
	git diff --exit-code index.html rss.xml

wireframes:
	python scripts/gen_wireframes.py
