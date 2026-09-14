FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY publish/ /app/
USER 10001
EXPOSE 8080
ENTRYPOINT ["dotnet","App.dll"]
