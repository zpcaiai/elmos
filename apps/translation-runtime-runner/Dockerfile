# The operator must supply a verified digest-pinned image containing the exact
# Python/native toolchains AND Node/web dependencies. No default runtime exists.
ARG ELMOS_TRANSLATION_BASE_IMAGE
FROM ${ELMOS_TRANSLATION_BASE_IMAGE}
WORKDIR /opt/elmos
COPY engines/polyglot-route-engine /opt/elmos/engines/polyglot-route-engine
COPY apps/web-console/app/lib /opt/elmos/apps/web-console/app/lib
COPY apps/web-console/package.json /opt/elmos/apps/web-console/package.json
COPY contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json \
     /opt/elmos/contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json
COPY apps/translation-runtime-runner /opt/elmos/apps/translation-runtime-runner
ENV PYTHONPATH=/opt/elmos/engines/polyglot-route-engine/src \
    ELMOS_POLYGLOT_ROUTE_CONTAINER_PROFILE=linux-arm64-python3.12.12-node26-typescript5.9.2-v1 \
    HOME=/elmos/tmp/home \
    TMPDIR=/elmos/tmp
ENTRYPOINT ["node", "--loader", "/opt/elmos/apps/translation-runtime-runner/ts-loader.mjs", "/opt/elmos/apps/translation-runtime-runner/entrypoint.mjs"]
