"""
Easy BDD Framework - Main package
"""

__version__ = "1.0.0"
__author__ = "Your Team"

from .core.yaml_compat import patch_yaml_bool_resolver

patch_yaml_bool_resolver()

from .core.runner import TestRunner
from .core.parser import YAMLParser
from .core.generator import GherkinGenerator

__all__ = ["TestRunner", "YAMLParser", "GherkinGenerator"]
