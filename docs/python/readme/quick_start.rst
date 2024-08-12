.. _quick_start:

Quick Start
===========

The minimal operation of this Python-based ext_proc server requires the ``grpcio`` python package as well as the protobuf generator tool `[buf] <https://buf.build/docs/introduction>`_.

The preferred method of installation is through a virtual environment, ``venv``.

Setup
-----

1. **Virtual Environment Setup**:

    .. code-block:: shell

        cd service-extensions/callouts/python
        python -m venv env
        source env/bin/activate

2. **Install Packages**:

    .. code-block:: shell

        pip install -r requirements.txt

3. **Install buf**:

    Install ``buf`` from `here <https://buf.build/docs/installation>`_.

4. **Generate Proto Files**:

    The proto library files are generated with ``buf`` using:

    .. code-block:: shell

        buf -v generate \
          https://github.com/envoyproxy/envoy.git#subdir=api \
          --path envoy/service/ext_proc/v3/external_processor.proto \
          --include-imports

    The default template file ``buf.gen.yaml`` will not generate ``pyright`` compatible proto stubs.

    If you plan to develop callouts with a similar type checker and not just build them,
    we suggest you run the command with the alternative development template using
    ``--template=buf_dev.gen.yaml``:

    .. code-block:: shell

        buf -v generate \
          https://github.com/envoyproxy/envoy.git#subdir=api \
          --path envoy/service/ext_proc/v3/external_processor.proto \
          --include-imports --template=buf_dev.gen.yaml

    You may need to run ``python -m pip uninstall ./protodef`` after re-generating the proto files to get the linter to update.

    The proto files are then installed as a local package:

    .. code-block:: shell

        python -m pip install ./protodef

    We install the proto files as a local package to allow for absolute imports within the generated python code.

Running the Server
------------------

Start example servers from the ``extproc/example/<...>`` submodules. For example, start the grpc ``service_callout_example`` server with:

.. code-block:: shell

    python -m extproc.example.grpc.service_callout_example

The server will run until interrupted (e.g., with ``Ctrl-C``).

Examples
--------

Examples for various styles of callout servers are located under ``extproc/example/``.
