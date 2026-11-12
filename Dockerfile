FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MT_DATA_DIR=/app/data
EXPOSE 8000 8501
CMD ["uvicorn", "marketing_team.server:app", "--host", "0.0.0.0", "--port", "8000"]
