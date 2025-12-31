FROM python:3.11-slim
WORKDIR /app
COPY services/gateway_api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8057
CMD ["uvicorn","services.gateway_api.main:app","--host","0.0.0.0","--port","8057"]
