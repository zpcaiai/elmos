FROM python:3.12-slim
WORKDIR /app
RUN useradd -r -u 10001 elmos
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
USER 10001
EXPOSE 8000
CMD ["python","-m","app"]
