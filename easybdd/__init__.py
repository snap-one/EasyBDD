"""
Easy BDD Framework - Main package
"""

__version__ = "1.0.0"
__author__ = "Your Team"

from .core.runner import TestRunner
from .core.parser import YAMLParser
from .core.generator import GherkinGenerator

__all__ = ["TestRunner", "YAMLParser", "GherkinGenerator"]
