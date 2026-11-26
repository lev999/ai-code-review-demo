.PHONY: setup smoke component api browser verify

setup:
	npm ci --prefix web

smoke:
	python3 -m unittest discover -s tests -v

component:
	node --test web/tests/task_state.test.js

api:
	python3 -m unittest discover -s api/tests -p 'test_*.py' -v

browser:
	CHROME_CHANNEL=chrome node scripts/run_browser_tests.mjs

# Run every check and retain each result, including when one check fails.
verify:
	@$(MAKE) --no-print-directory smoke; smoke_status=$$?; \
	$(MAKE) --no-print-directory component; component_status=$$?; \
	$(MAKE) --no-print-directory api; api_status=$$?; \
	$(MAKE) --no-print-directory browser; browser_status=$$?; \
	if [ "$$smoke_status" -ne 0 ] || [ "$$component_status" -ne 0 ] || [ "$$api_status" -ne 0 ] || [ "$$browser_status" -ne 0 ]; then exit 1; fi
