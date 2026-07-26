#!/bin/sh
set -eu

mkdir -p /home/elmos/.m2/repository
cp -R /opt/elmos/maven-seed/. /home/elmos/.m2/repository/
exec java -XX:MaxRAMPercentage=70 -jar /app/app.jar
