# Base Python image
FROM python:3.11-slim

# Working directory එක සකස් කිරීම
WORKDIR /app

# Environment variables සකස් කිරීම
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies install කිරීම
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements file එක Copy කර dependencies install කිරීම
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code එක copy කිරීම
COPY . .

# FastAPI Port එක expose කිරීම
EXPOSE 8000

# Application එක run කිරීම
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]