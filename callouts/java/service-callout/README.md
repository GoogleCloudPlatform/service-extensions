# Java Callout Server

## Pre-requirements

### Install Java

Before you can build this project, you need to have Java 17 installed. Here are some resources to guide you through the installation process:

- [Install Java on Windows](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-microsoft-windows-platforms.html)
- [Install Java on macOS](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-macos.html)
- [Install Java on Linux](https://docs.oracle.com/en/java/javase/17/install/installation-jdk-linux-platforms.html)

### Set JAVA_HOME

After installing Java, you need to set the `JAVA_HOME` environment variable to point to your Java installation. Here are guides for different operating systems:

- **Windows**
    1. Open the Start Search, type in "env", and select "Edit the system environment variables".
    2. In the System Properties window, click on the "Environment Variables" button.
    3. Under System Variables, click "New" and enter `JAVA_HOME` as the variable name and the path to your JDK installation as the variable value (e.g., `C:\Program Files\Java\jdk-17`).
    4. Click OK and apply the changes.

- **macOS**
    1. Open a terminal window.
    2. Open or create the file `~/.bash_profile` or `~/.zshrc` (depending on your shell).
    3. Add the following line to the file:
       ```sh
       export JAVA_HOME=$(/usr/libexec/java_home -v 17)
       ```
    4. Save the file and run `source ~/.bash_profile` or `source ~/.zshrc`.

- **Linux**
    1. Open a terminal window.
    2. Open or create the file `~/.bashrc` or `~/.profile`.
    3. Add the following line to the file:
       ```sh
       export JAVA_HOME=/path/to/your/jdk-17
       export PATH=$JAVA_HOME/bin:$PATH
       ```
    4. Save the file and run `source ~/.bashrc` or `source ~/.profile`.


## Build Instructions

This project is using the maven build system.

From the main directory, build with:

```
mvn clean package
```

## Running a Specific Class Locally
Before running the command, ensure that you have configured Java correctly and set the `JAVA_HOME` environment variable properly. You can verify this by running the following commands in your terminal:

```sh
java -version
```

To run a specific class inside the `example` package (which contains various use cases), you can use the `java` command. For instance, to run the `BasicCalloutServer` class, use the following command:

```sh
java -cp target/service-callout-1.0-SNAPSHOT-jar-with-dependencies.jar example.BasicCalloutServer
```

## Docker

### Build the Docker Image

Execute the following command to build the Docker image. Replace `service-callout:1.0-SNAPSHOT` with your preferred image name and tag if necessary.

```sh
docker build -t service-callout:1.0-SNAPSHOT .
```

### Running the Docker Container

To run the BasicCalloutServer class for example, use the following command:

```sh
docker run -p 80:80 -p 443:443 service-callout:1.0-SNAPSHOT example.BasicCalloutServer
```

### Running with JVM Options

If you need to pass JVM options (e.g., setting the maximum heap size), use the -e JAVA_OPTS flag:

```sh
docker run -p 80:80 -p 443:443 \
 -e JAVA_OPTS="-Xmx512m" \
 service-callout:1.0-SNAPSHOT example.BasicCalloutServer
```

### Available Examples

- AddBody
- AddHeader
- BasicCalloutServer
- JwtAuth
- Redirect


## Developing Callouts
This repository provides the following files to be extended to fit the needs of the user:

[ServiceCallout](src/main/java/service/ServiceCallout.java): Baseline service callout server.

[ServiceCalloutTools](src/main/java/service/ServiceCalloutTools.java): Common functions used in many callout server code paths.

### Making a New Server

Create a new Java file Example.java and import the ``ServiceCallout`` class from service.ServiceCallout:

```java
import service.ServiceCallout;
```
### Extend the CalloutServer

Create a custom class extending ``ServiceCallout``:

```java
public class Example extends ServiceCallout {}
```

Create the constructor for the superclass constructor:

```java
// Constructor that calls the superclass constructor
public Example(Example.Builder builder) {
    super(builder);
}
```

Add the Builder for your example:

```java
// Constructor that calls the superclass constructor
public Example(Example.Builder builder) {
  super(builder);

  // Builder specific to Example
  public static class Builder extends ServiceCallout.Builder<Example.Builder> {

    @Override
    public Example build() {
      return new Example(this);
    }

    @Override
    protected Example.Builder self() {
      return this;
    }
  }
}
```

Add the method you are going to override for your custom processing  (e.g: Request Headers):
```java

@Override
public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder,
                             HttpHeaders headers) {
}
```

### Run the Server

Create an instance of your custom server and call the start method:

```java
public static void main(String[] args) throws Exception {
    // Create a builder for ServiceCallout with custom configuration
    Example server = new Example.Builder()
            .build();

    // Start the server and block until shutdown
    server.start();
    server.blockUntilShutdown();
}
```

Custom configuration is also enabled, so it is possible to change the default ip and port for example:
```java
public static void main(String[] args) throws Exception {
    // Create a builder for ServiceCallout with custom configuration
    Example server = new Example.Builder()
            .setIp("111.222.333.444")       // Customize IP
            .setPort(8443)                  // Set the port for secure communication
            .build();

    // Start the server and block until shutdown
    server.start();
    server.blockUntilShutdown();
}
```

## Documentation

Javadoc is a tool provided by Java for generating API documentation in HTML format from Java source code. 

We use the `maven-javadoc-plugin` plugin to generate Javadoc documentation automatically.

### Execute Javadoc Command

To generate Javadoc documentation, you can run the following Maven command in your terminal:

```sh
mvn javadoc:javadoc
```

This command will generate Javadoc for your project, including dependencies, and store the output in the `target/docs/apidocs`
directory configured inside `reportOutputDirectory` in the `pom.xml`.

You may open the file `target/docs/apidocs/index.html` in order to see the documentation.
