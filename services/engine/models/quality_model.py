"""
TradeForge Quality Model Interface.
Rule 5 & Master Prompt:
The ML quality model acts strictly as a secondary filter.
It NEVER invents fake probabilities.
The default model is explicit NO_MODEL pass-through that reports None (no probability).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class QualityModel(ABC):
    """
    Abstract interface for secondary trade signal quality scoring.
    Must output probability in [0.0, 1.0] or None if un-scored.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name or version tag of the scoring model."""
        pass

    @abstractmethod
    def score_signal(self, features: Dict[str, Any]) -> Optional[float]:
        """
        Evaluate signal setup features.
        Returns predicted win probability [0.0, 1.0] or None when no model is active.
        """
        pass


class NoModelPassThrough(QualityModel):
    """
    Default QualityModel implementation.
    Rule: Never report a fake score. Explicitly passes through without probability (None).
    """

    @property
    def model_name(self) -> str:
        return "NO_MODEL"

    def score_signal(self, features: Dict[str, Any]) -> Optional[float]:
        # Rule: Explicit NO_MODEL pass-through that reports no probability, never a fake one.
        return None
