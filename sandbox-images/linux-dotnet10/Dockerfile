ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --create-home elmos
WORKDIR /workspace
USER 10001:10001
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 NUGET_PACKAGES=/workspace/.nuget/packages
ENTRYPOINT ["dotnet"]
