FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nomus/ nomus/
COPY data/templates/ data/templates/

EXPOSE 8000

CMD ["python", "-m", "nomus.bot.main"]
