from __future__ import annotations

from typing import Any

from backend.learning import ACTION_IDS, PolicyDecision, rule_policy


class TeachingPolicy:
    def select_action(self, features: dict[str, float], valid_actions: list[str]) -> PolicyDecision:
        raise NotImplementedError


class RuleTeachingPolicy(TeachingPolicy):
    def select_action(self, features: dict[str, float], valid_actions: list[str]) -> PolicyDecision:
        return rule_policy(features, valid_actions)


class DqnTeachingPolicy(TeachingPolicy):
    """Optional lazy DQN adapter; it never changes progression or lesson facts."""

    def __init__(self, action_ids: list[str] | None = None):
        self.action_ids = action_ids or ACTION_IDS
        try:
            import torch  # type: ignore[import-not-found]
            from torch import nn
            self._torch = torch
            self._network = nn.Sequential(nn.Linear(5, 16), nn.ReLU(), nn.Linear(16, len(self.action_ids)))
        except ImportError:
            self._torch = None
            self._network = None

    @property
    def available(self) -> bool:
        return self._network is not None

    def select_action(self, features: dict[str, float], valid_actions: list[str]) -> PolicyDecision:
        if not self.available or not valid_actions:
            return rule_policy(features, valid_actions)
        values = [features.get("attempt_count", 0.0), features.get("correctness_ema", 0.0), features.get("hint_use_rate", 0.0), features.get("revisit_count", 0.0), features.get("independence_score", 0.0)]
        torch_module: Any = self._torch
        network: Any = self._network
        with torch_module.no_grad():
            scores = network(torch_module.tensor([values], dtype=torch_module.float32))[0]
        ranked = sorted(((float(scores[index]), action) for index, action in enumerate(self.action_ids) if action in valid_actions), reverse=True)
        return PolicyDecision(ranked[0][1], "dqn-untrained-candidate", "highest_q_value", False)
