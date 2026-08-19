"""NLP module — analysis parser and auto pros/cons generator (Sprint 5)."""

from .parser import crosscheck_cagr, parse_analysis, parse_text
from .pros_cons_generator import ProsConsGenerator

__all__ = ["ProsConsGenerator", "crosscheck_cagr", "parse_analysis", "parse_text"]
