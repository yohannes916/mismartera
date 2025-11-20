"""
🧠 AnalysisEngine Module

AI-powered trading analysis and decision making.

Responsibilities:
- Calculate evaluation metrics
- Consult with LLMs (Claude, GPT-4, etc.)
- Generate success probability
- Make buy/sell/exit decisions
- Optimize weights
- Log all analysis with LLM interaction details

Supports both Real and Backtest modes.
"""

from app.managers.analysis_engine.api import AnalysisEngine

__all__ = ['AnalysisEngine']
