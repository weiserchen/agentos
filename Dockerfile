FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY src /app/src

# create non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8100
EXPOSE 8101

CMD ["python", "src/main.py"]