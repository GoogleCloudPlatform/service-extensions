.. _docker:

Docker
======

Building Docker Images
----------------------

The basic Docker image contains arguments for pointing to and running python modules.

Example to build ``extproc/example/basic_callout_server.py``:

.. code-block:: shell

    docker build \
        -f ./extproc/example/Dockerfile \
        -t service-callout-example-python \
        --build-arg copy_path=extproc/example/basic_callout_server.py \
        --build-arg run_module=basic_callout_server .

``--build-arg`` specifies the following:

* ``copy_path``: Path of python files required on the docker image.
* ``run_module``: The module to run on startup.

The image copies ``extproc/example/basic_callout_server.py`` to the base directory and runs it as ``basic_callout_server``.

Run the image:

.. code-block:: shell

    docker run -P -it --network host service-callout-example-python:latest

In this example, using the ``-P`` flag tells docker to connect the exposed ports to the local machine's ports.
Setting ``--network host`` tells docker to connect the image to the ``0.0.0.0`` or ``localhost`` ip address.

``[!NOTE]``
The docker image is set up to pass command line arguments to the module when specified.
This also requires that the example is set up to use command line arguments like in
``basic_callout_server.py``

For example:

.. code-block:: shell

    docker run -P -it --network host service-callout-example-python:latest \
        -- --combined_health_check

Will run the health check for ``basic_callout_server`` combined with the main grpc server.


Custom Docker Files
-------------------

If the baseline docker file does not contain the required complexity for a given use case.
A custom image can be created and branched from the provided Dockerfile.
The file is internally split up into two steps, the base image and the example specific image.

For instance, the ``jwt_auth`` example requires an additional python library.
The Dockerfile within that example directory installs that package as part of the image setup.

Build the base image:

.. code-block:: shell

    docker build \
        -f ./extproc/example/Dockerfile \
        --target service-callout-common-python \
        -t service-callout-common-python .

Build the ``jwt_auth`` image:

.. code-block:: shell

    docker build \
        -f ./extproc/example/jwt_auth/Dockerfile \
        -t service-callout-jwt-example-python .
