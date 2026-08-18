"""NLP module — analysis parser and auto pros/cons generator (Sprint 5)."""

from .parser import parse_analysis, parse_text, crosscheck_cagr
from .pros_cons_generator import ProsConsGenerator

__all__ = ["parse_analysis", "parse_text", "crosscheck_cagr", "ProsConsGenerator"]
