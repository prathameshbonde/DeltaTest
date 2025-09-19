FROM python:3.12-slim
WORKDIR /app
COPY selector-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY selector-service/app ./app
EXPOSE 8000
ENV LLM_MODE=mock
CMD ["python", "-m", "app.main"]
