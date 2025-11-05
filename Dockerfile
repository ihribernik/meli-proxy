FROM python:3.12-slim-trixie

WORKDIR /code/app

# Install only runtime dependencies first to leverage Docker cache
COPY requirements.txt /code/app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source
COPY . /code/app/

CMD ["uvicorn", "app.fast_api:app", "--host", "0.0.0.0", "--port", "8000"]

