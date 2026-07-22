FROM maven:3.9.11-eclipse-temurin-8@sha256:e3c149f44c95b0e9dd131862b3df67b3f061f7f6f3898a87b170564b3a943611
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --home-dir /home/elmos --create-home --shell /usr/sbin/nologin elmos \
    && install -d -o 10001 -g 10001 /workspace /artifacts /home/elmos/.m2
ENV HOME=/home/elmos LANG=C.UTF-8 TZ=UTC
USER 10001:10001
WORKDIR /workspace
CMD ["sleep", "infinity"]
