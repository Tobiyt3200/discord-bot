# Use a slim Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the code
COPY . .

# Set environment variable for unbuffered logs (optional)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "bot.py"]
