FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/data /app/data/screenshots
RUN chmod +x /app/scripts/start_railway.sh

EXPOSE 8000

CMD ["python", "run_web.py"]
