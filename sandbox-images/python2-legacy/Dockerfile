FROM python:2.7.18-buster@sha256:d8fac68ebdc45b8d66d53f1ed6c1532da81109a8f5532a6ca0c951ed31107d70
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --create-home elmos
USER 10001:10001
WORKDIR /workspace
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python2.7"]

