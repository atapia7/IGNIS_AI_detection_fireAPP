FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs assets

EXPOSE 8502

CMD streamlit run app.py \
    --server.port=${PORT:-8502} \
    --server.address=0.0.0.0 \
    --server.headless=true
