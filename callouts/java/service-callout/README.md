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

From this directory, build with:

```
mvn install
```

## Running a Specific Class Locally
Before running the command, ensure that you have configured Java correctly and set the `JAVA_HOME` environment variable properly. You can verify this by running the following commands in your terminal:

```sh
java -version
```

To run a specific class inside the `example` package (which contains various use cases), you can use the `mvn exec:java` command. For instance, to run the `BasicCalloutServer` class, use the following command:

```sh
mvn exec:java -Dexec.mainClass="example.BasicCalloutServer"
```

## Documentation

Javadoc is a tool provided by Java for generating API documentation in HTML format from Java source code. 

We use the `maven-javadoc-plugin` plugin to generate Javadoc documentation automatically.

### Execute Javadoc Command:

To generate Javadoc documentation, you can run the following Maven command in your terminal:

```sh
mvn javadoc:javadoc
```

This command will generate Javadoc for your project, including dependencies, and store the output in the `target/docs/apidocs`
directory configured inside `reportOutputDirectory` in the `pom.xml`.

You may open the file `target/docs/apidocs/index.html` in order to see the documentation.
