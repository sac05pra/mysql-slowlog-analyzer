# Dockerfile

# --- Stage 1: Base Image ---
# Use an official Python runtime as a parent image. The 'slim' version is smaller.
FROM python:3.11-slim

# --- Stage 2: Install System Dependencies ---
# Install pt-query-digest from the Percona Toolkit. This is a non-Python dependency.
# 'apt-get update' refreshes the package list.
# 'apt-get install -y' installs packages without asking for confirmation.
# '--no-install-recommends' avoids installing optional packages, keeping the image small.
# 'rm -rf /var/lib/apt/lists/*' cleans up the package cache afterward.
RUN apt-get update && apt-get install -y --no-install-recommends percona-toolkit \
    && rm -rf /var/lib/apt/lists/*

# --- Stage 3: Python Environment Setup ---
# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies specified in requirements.txt
# Using --no-cache-dir makes the image slightly smaller.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade -r requirements.txt

# --- Stage 4: Copy Application Code ---
# Copy the rest of your application code into the container's working directory
COPY . .

ENV AWS_REGION=eu-west-2
# --- Stage 5: Final Configuration ---
# Expose the port your app will run on. This must match the Gunicorn port.
EXPOSE 5050

# The command to run your application using the Gunicorn production server.
# It means: run gunicorn, bind it to all network interfaces on port 5050,
# and run the 'app' object found inside the 'app.py' file.
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "app:app"]
