FROM mirror.gcr.io/library/maven@sha256:fa7aa19829157d299ff05f631b51697a388dcd2f6955e84249ecc652015f217b

LABEL io.elmos.evidence-class="LOCAL_NON_CERTIFYING" \
      io.elmos.repository="retro-game" \
      io.elmos.platform="linux/amd64" \
      io.elmos.source-commit="3d08c4b2ca814acfd873fc7874f724089e5b1d85"

ARG DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g; s|http://security.ubuntu.com|https://security.ubuntu.com|g' \
        /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get \
        -o Acquire::Retries=5 \
        -o Acquire::https::Timeout=60 \
        update \
    && apt-get \
        -o Acquire::Retries=5 \
        -o Acquire::https::Timeout=60 \
        install --yes --no-install-recommends \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*
