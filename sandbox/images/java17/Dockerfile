FROM maven:3.9.11-eclipse-temurin-17@sha256:e4a7ace3dc0d645ed97f8d9ad0b0d3f0b14fa8d150138f27f116d7105a639b82
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --home-dir /home/elmos --create-home --shell /usr/sbin/nologin elmos \
    && install -d -o 10001 -g 10001 /workspace /artifacts /home/elmos/.m2
ENV HOME=/home/elmos LANG=C.UTF-8 TZ=UTC
USER 10001:10001
WORKDIR /workspace
CMD ["sleep", "infinity"]
