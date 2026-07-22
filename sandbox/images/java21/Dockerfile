FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --home-dir /home/elmos --create-home --shell /usr/sbin/nologin elmos \
    && install -d -o 10001 -g 10001 /workspace /artifacts /home/elmos/.m2
ENV HOME=/home/elmos LANG=C.UTF-8 TZ=UTC
USER 10001:10001
WORKDIR /workspace
CMD ["sleep", "infinity"]
