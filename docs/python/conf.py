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

import os
import sys
sys.path.insert(0, os.path.abspath('../../'))

# -- Project information -----------------------------------------------------

project = "Google Cloud Service Extensions Samples"
copyright = "2024, Google LLC"
author = "Google"

# -- General configuration ---------------------------------------------------

extensions = [
    # API doc generation
    "sphinx.ext.autodoc",
    # Automatically generate autodoc API docs
    "sphinx.ext.autosummary",
    # Support for google-style docstrings
    "sphinx.ext.napoleon",
    # Add links to source from generated docs
    "sphinx.ext.viewcode",
    # Link to other sphinx docs
    "sphinx.ext.intersphinx",
    # Support external links to different versions in the Github repo
    "sphinx.ext.extlinks",
    # Rendered graphviz graphs
    "sphinx.ext.graphviz",
]

autodoc_mock_imports = ["envoy", "extproc"]

templates_path = ['_templates']

html_static_path = ['_static']

html_css_files = ['custom.css']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**/venv"]

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'

html_static_path = ['_static']

html_css_files = ['custom.css']

html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': 4,
    'titles_only': False
}

html_context = {
    "display_github": True,  # Integrate GitHub
    "github_user": "GoogleCloudPlatform",  # Username
    "github_repo": "service-extensions-samples",  # Repo name
    "github_version": "main",  # Version
    "conf_py_path": "/docs/",  # Path in the checkout to the docs root
}
