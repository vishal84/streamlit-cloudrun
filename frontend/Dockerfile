# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
ENV PORT 8080

# Set the working directory in the container
WORKDIR $APP_HOME

# Copy the dependencies file (note the space before the dot)
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code (note the space between dots)
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Command to run the Streamlit application
# Replace 'app.py' with the name of your main Streamlit file
CMD ["/bin/sh", "-c", "streamlit run app.py --server.port=$PORT --server.enableCORS=false --server.enableXsrfProtection=false"]