SHELL := /bin/bash

.PHONY: validate test install list routes

validate:
	./validate.sh

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

install:
	@test -n "$(TARGET)" || (echo "usage: make install TARGET=/path/to/elmos" && exit 2)
	./install.sh "$(TARGET)"

list:
	python3 scripts/elmos_skills.py list-skills

routes:
	python3 scripts/elmos_skills.py routes
