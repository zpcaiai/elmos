.PHONY: dev down logs verify demo java-engine clean

dev:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

verify:
	./scripts/verify.sh

demo:
	curl -fsS -X POST http://localhost:8080/api/v1/demo/bootstrap | python3 -m json.tool

java-engine:
	cd engines/java-engine && mvn -q -pl engine-cli -am package
	cd engines/java-engine && java -jar engine-cli/target/java-engine-cli.jar ../../samples/java-sample /tmp/psp.json
	cat /tmp/psp.json

clean:
	find . -type d \( -name build -o -name target -o -name .next -o -name node_modules -o -name .venv \) -prune -exec rm -rf {} +

-include Makefile.batch29

-include Makefile.batch30

-include Makefile.batch31

include Makefile.batch32

include Makefile.batch33

include Makefile.batch34

include Makefile.batch35

include Makefile.batch36

include Makefile.batch37
