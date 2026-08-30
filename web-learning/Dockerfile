FROM python:3.12-slim
WORKDIR /app
COPY app.py course_public.json ./
COPY static ./static
RUN mkdir -p /app/data
ENV PORT=3001 LEARNING_DB=/app/data/learning.sqlite3 PYTHONUNBUFFERED=1
EXPOSE 3001
CMD ["python3", "app.py"]
