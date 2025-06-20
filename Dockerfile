FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY app.py ./

# Expose port and run
EXPOSE 5000
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "app:app"]