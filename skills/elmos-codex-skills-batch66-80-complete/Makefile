.PHONY: validate test install
validate:
	./validate.sh
test:
	python3 -m unittest discover -s tests -p 'test_*.py'
install:
	./install.sh "$${HOME}/.codex/skills"
