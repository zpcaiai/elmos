FROM maven:3.9.11-eclipse-temurin-11@sha256:c095e2421eaf3e5cb1573fd0474e68e17062866d454362349e17bbb75f44031e
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --home-dir /home/elmos --create-home --shell /usr/sbin/nologin elmos \
    && install -d -o 10001 -g 10001 /workspace /artifacts /home/elmos/.m2
ENV HOME=/home/elmos LANG=C.UTF-8 TZ=UTC
USER 10001:10001
WORKDIR /workspace
CMD ["sleep", "infinity"]
