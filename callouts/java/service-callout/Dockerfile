# Copyright 2024 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Stage 1: Build the Java application using Maven
FROM maven:3.8.5-openjdk-17 AS builder

# Set the working directory inside the container
WORKDIR /app

# Copy the pom.xml and download dependencies
COPY pom.xml .
RUN mvn dependency:go-offline

# Copy the source code
COPY src ./src

# Build the application
RUN mvn clean package -DskipTests

# Stage 2: Create the runtime image
FROM marketplace.gcr.io/google/debian12

# Install necessary dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the JAR from the builder stage and rename it to app.jar
COPY --from=builder /app/target/service-callout-1.0-SNAPSHOT-jar-with-dependencies.jar app.jar

# Copy certificates
COPY src/main/resources/certs ./certs

# Expose necessary ports
EXPOSE 80 443 8080

# Environment variable for JVM options (optional)
ENV JAVA_OPTS=""

# Create a non-root user for running the application
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Change ownership and switch to the non-root user
RUN chown -R appuser:appgroup /app
USER appuser

# Entry point to run the application
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -cp app.jar $0 $@"]

# Default command
CMD []