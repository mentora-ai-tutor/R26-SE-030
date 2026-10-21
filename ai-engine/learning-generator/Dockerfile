FROM python:3.11-slim

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends default-jdk-headless && \
    rm -rf /var/lib/apt/lists/* && \
    java -version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5010"]
