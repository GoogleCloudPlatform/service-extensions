.. _alternative_install_methods:

Alternative Install Methods
===========================

Without venv
----------------

Install packages through the package manager:

.. code-block:: shell

    sudo apt-get install python3-grpcio -y
    python -m pip install ./protodef

.. warning::

    Installing the ``protodef`` package to your system outside of a ``venv`` could cause unintentional side effects.

Without Installing Proto Code as a Local Package
------------------------------------------------

Alternatively, rather than installing through pip, the proto code can be placed in the root of this project and imported directly.

.. code-block:: bash

    buf -v generate \
      https://github.com/envoyproxy/envoy.git#subdir=api \
      --path envoy/service/ext_proc/v3/external_processor.proto \
      --include-imports \
      -o out && \
    mv ./out/protodef/* .
