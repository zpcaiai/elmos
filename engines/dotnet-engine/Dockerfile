FROM mcr.microsoft.com/dotnet/sdk:10.0.301-noble AS build
WORKDIR /source
COPY engines/dotnet-engine/ ./
RUN dotnet publish src/Elmos.Dotnet.Worker/Elmos.Dotnet.Worker.csproj -c Release -o /out --no-self-contained

FROM mcr.microsoft.com/dotnet/aspnet:10.0.9-noble
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --create-home elmos && mkdir -p /workspaces && chown 10001:10001 /workspaces
USER 10001:10001
WORKDIR /app
COPY --from=build /out ./
ENV ASPNETCORE_URLS=http://0.0.0.0:8086 ELMOS_DOTNET_WORKSPACE_ROOT=/workspaces DOTNET_CLI_TELEMETRY_OPTOUT=1
EXPOSE 8086
ENTRYPOINT ["dotnet", "Elmos.Dotnet.Worker.dll"]
