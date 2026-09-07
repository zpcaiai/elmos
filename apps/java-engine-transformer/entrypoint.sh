#!/bin/sh
set -eu

exec java -XX:MaxRAMPercentage=70 -jar /app/app.jar
