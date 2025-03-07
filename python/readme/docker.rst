.. _docker:

Docker
======

Building Docker Images
----------------------

The basic Docker image contains arguments for pointing to and running python modules.

For example, to build ``extproc/example/basic/service_callout_example.py`` run:

.. code-block:: shell

    docker build \
        -f ./extproc/example/Dockerfile \
        -t service-callout-example-python \
        --build-arg copy_path=extproc/example/basic/ \
        --build-arg run_module=service_callout_example .

``--build-arg`` specifies the following:

* ``copy_path``: Required files to copy to the docker image.
* ``run_module``: The python module to run on startup.

The above example makes a copy of ``extproc/example/basic/service_callout_example.py``
and sets up the image to run ``service_callout_example.py`` on startup.

The image can then be run with:

.. code-block:: shell

    docker run -P -it --network host service-callout-example-python:latest

In this example, using the ``-P`` flag tells docker to connect the exposed ports to the local machine's ports.
Setting ``--network host`` tells docker to connect the image to the ``0.0.0.0`` or ``localhost`` ip address.

.. note::

    The docker image is set up to pass command line arguments to the module when specified.
    This also requires that the example is set up to use command line arguments as well,
    like in ``basic/service_callout_example.py``

For example:

.. code-block:: shell

    docker run -P -it --network host service-callout-example-python:latest \
        -- --combined_health_check

Will run the health check for ``basic/service_callout_example.py`` combined with the main grpc server.


Examples with unique dependencies
---------------------------------

The ``cloud_log`` and ``jwt_auth`` examples require additional libraries to function.
For instance, the ``cloud_log`` example requires the ``google-cloud-logging`` library.
In this case, we need more than just the python file.
We copy ``additional-requirements.txt`` along with ``service_callout_example.py`` by
specifying the folder ``extproc/example/cloud_log`` as the ``copy_path``.

.. code-block:: shell

    docker build \
        -f ./extproc/example/Dockerfile \
        -t service-callout-example-python \
        --build-arg copy_path=extproc/example/cloud_log \
        --build-arg run_module=service_callout_example .

``./extproc/example/Dockerfile`` is set up to detect additional dependencies when present,
and install them.

Both the ``cloud_log`` and ``jwt_auth`` examples can be built this way.
If even more configurability is needed, a custom Docker image example is also available.


Custom Docker Files
-------------------

If the baseline docker file does not contain the required complexity for a given use case.
A custom image can be created and branched from the common image.
``./extproc/example/Dockerfile`` is internally split up into two steps,
a common image step and the example specific image step.

For instance, the ``jwt_auth`` example requires an additional python library much like ``cloud_log``.
We can also accomplish the same goal as the ``cloud_log`` example through a custom Docker image.
``./extproc/example/jwt_auth/Dockerfile`` installs the dependencies as part of the image setup.

To build the ``jwt_auth`` example we first build the common image:

.. code-block:: shell

    docker build \
        -f ./extproc/example/Dockerfile \
        --target service-callout-common-python \
        -t service-callout-common-python .

and then the ``jwt_auth`` image:

.. code-block:: shell

    docker build \
        -f ./extproc/example/jwt_auth/Dockerfile \
        -t service-callout-jwt-example-python .
