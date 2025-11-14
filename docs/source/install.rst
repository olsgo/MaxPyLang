=============
Installation
=============

Requirements
============

- Python 3.7 or higher
- MaxMSP (for opening and running the generated patches)

Dependencies
------------

MaxPyLang requires the following Python packages:

- numpy >= 1.22.0
- sphinx_rtd_theme
- tabulate

These will be automatically installed when you install MaxPyLang.

Installation from Source
=========================

The recommended way to install MaxPyLang is from the GitHub repository:

.. code-block:: bash

    git clone https://github.com/Barnard-PL-Labs/MaxPy-Lang.git
    cd MaxPy-Lang
    pip3 install .

Development Installation
========================

If you want to modify the source code and see changes immediately, install in editable mode:

.. code-block:: bash

    git clone https://github.com/Barnard-PL-Labs/MaxPy-Lang.git
    cd MaxPy-Lang
    pip3 install -e .

This creates a link to your source directory, so any changes you make are immediately available without reinstalling.

Verifying Installation
=======================

To verify MaxPyLang is installed correctly, run the hello world example:

.. code-block:: bash

    cd examples/hello_world
    python3 main.py

This should create a file called ``hello_world.maxpat`` in the current directory. Open this file in MaxMSP to verify it works correctly.

Troubleshooting
===============

Import Error
------------

If you get ``ModuleNotFoundError: No module named 'maxpylang'``, make sure:

1. You installed the package successfully
2. You're using the correct Python environment (check with ``which python3``)
3. If using a virtual environment, ensure it's activated

Dependency Issues
-----------------

If you have issues with numpy or other dependencies, try upgrading pip first:

.. code-block:: bash

    pip3 install --upgrade pip
    pip3 install .

Python Version
--------------

MaxPyLang requires Python 3.7 or higher. Check your version:

.. code-block:: bash

    python3 --version

If you need to install a newer Python version, visit https://www.python.org/downloads/
