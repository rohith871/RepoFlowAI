from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

torch: Any = None
torch_nn: Any = None
try:
    import torch as _torch
    from torch import nn as _torch_nn
    torch = _torch
    torch_nn = _torch_nn
except ImportError:  # pragma: no cover - exercised in minimal API installations
    class _MissingModule:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("PyTorch is required for adaptive policy training")

    class _MissingNN:
        Module = _MissingModule

    torch_nn = _MissingNN()

from backend.learning import ACTION_IDS, PolicyDecision

STATE_KEYS = ["attempt_count", "correctness_ema", "hint_use_rate", "revisit_count", "independence_score"]


class TeachingQNetwork(torch_nn.Module):
    def __init__(self, action_count: int = len(ACTION_IDS)):
        super().__init__()
        self.layers = torch_nn.Sequential(torch_nn.Linear(len(STATE_KEYS), 32), torch_nn.ReLU(), torch_nn.Linear(32, 32), torch_nn.ReLU(), torch_nn.Linear(32, action_count))

    def forward(self, state: Any) -> Any:
        return self.layers(state)


def _require_torch() -> Any:
    if torch is None:
        raise RuntimeError("PyTorch is required for adaptive policy training")
    return torch


@dataclass(frozen=True)
class TrainingResult:
    checkpoint_path: str
    epochs: int
    loss: float
    evaluation: dict[str, Any]


def _vector(features: dict[str, float]) -> list[float]:
    return [float(features.get(key, 0.0)) for key in STATE_KEYS]


def profile_states() -> list[tuple[str, dict[str, float], int]]:
    return [
        ("novice", {"attempt_count": 1, "correctness_ema": .2, "hint_use_rate": .1, "revisit_count": 0, "independence_score": .2}, ACTION_IDS.index("hint_concept")),
        ("repeated_error", {"attempt_count": 4, "correctness_ema": .35, "hint_use_rate": .55, "revisit_count": 2, "independence_score": .25}, ACTION_IDS.index("show_source_excerpt")),
        ("developing", {"attempt_count": 3, "correctness_ema": .62, "hint_use_rate": .25, "revisit_count": 1, "independence_score": .58}, ACTION_IDS.index("ask_guided_question")),
        ("mastered", {"attempt_count": 6, "correctness_ema": .94, "hint_use_rate": .05, "revisit_count": 0, "independence_score": .92}, ACTION_IDS.index("ask_transfer_question")),
        ("returning", {"attempt_count": 2, "correctness_ema": .75, "hint_use_rate": .2, "revisit_count": 3, "independence_score": .7}, ACTION_IDS.index("replay_scene")),
    ]


def train_policy(checkpoint_path: Path, epochs: int = 250, seed: int = 7) -> TrainingResult:
    torch_module = _require_torch()
    random.seed(seed)
    torch_module.manual_seed(seed)
    model = TeachingQNetwork()
    optimizer = torch_module.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = torch_nn.CrossEntropyLoss()
    states = torch_module.tensor([_vector(state) for _, state, _ in profile_states()], dtype=torch_module.float32)
    targets = torch_module.tensor([target for _, _, target in profile_states()], dtype=torch_module.long)
    last_loss = 0.0
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(states), targets)
        loss.backward()
        optimizer.step()
        last_loss = float(loss.detach())
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch_module.save({"state_dict": model.state_dict(), "action_ids": ACTION_IDS, "state_keys": STATE_KEYS, "seed": seed}, checkpoint_path)
    evaluation = evaluate_checkpoint(checkpoint_path)
    return TrainingResult(str(checkpoint_path), epochs, last_loss, evaluation)


def evaluate_checkpoint(checkpoint_path: Path) -> dict[str, Any]:
    torch_module = _require_torch()
    payload = torch_module.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = TeachingQNetwork(len(payload["action_ids"]))
    model.load_state_dict(payload["state_dict"])
    model.eval()
    outcomes: list[dict[str, Any]] = []
    with torch_module.no_grad():
        for name, features, target in profile_states():
            scores = model(torch_module.tensor([_vector(features)], dtype=torch_module.float32))[0]
            action_index = int(torch_module.argmax(scores).item())
            outcomes.append({"profile": name, "expected_action": payload["action_ids"][target], "selected_action": payload["action_ids"][action_index], "correct": action_index == target})
    return {"profiles": outcomes, "accuracy": sum(1 for item in outcomes if item["correct"]) / len(outcomes), "model": "dqn-style-q-network", "checkpoint": str(checkpoint_path)}


class TrainedTeachingPolicy:
    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path
        self.model: TeachingQNetwork | None = None
        self.action_ids = ACTION_IDS
        self.version = "dqn-style-unavailable"
        self._load()

    def _load(self) -> None:
        if torch is None or not self.checkpoint_path.is_file():
            return
        torch_module = _require_torch()
        payload = torch_module.load(self.checkpoint_path, map_location="cpu", weights_only=False)
        self.action_ids = list(payload.get("action_ids", ACTION_IDS))
        model = TeachingQNetwork(len(self.action_ids))
        model.load_state_dict(payload["state_dict"])
        model.eval()
        self.model = model
        self.version = f"dqn-style-seed-{payload.get('seed', 'unknown')}"

    @property
    def available(self) -> bool:
        return self.model is not None

    def select_action(self, features: dict[str, float], valid_actions: list[str]) -> PolicyDecision:
        if self.model is None or not valid_actions:
            return PolicyDecision(valid_actions[0] if valid_actions else "continue_independent_attempt", self.version, "fallback", True)
        torch_module = _require_torch()
        with torch_module.no_grad():
            scores = self.model(torch_module.tensor([_vector(features)], dtype=torch_module.float32))[0]
        ranked = sorted(((float(scores[index]), action) for index, action in enumerate(self.action_ids) if action in valid_actions), reverse=True)
        if not ranked:
            return PolicyDecision("continue_independent_attempt", self.version, "no_valid_model_action", True)
        return PolicyDecision(ranked[0][1], self.version, "trained_q_value", False)


def write_training_report(result: TrainingResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checkpoint_path": result.checkpoint_path, "epochs": result.epochs, "loss": result.loss, "evaluation": result.evaluation}, indent=2), encoding="utf-8")
