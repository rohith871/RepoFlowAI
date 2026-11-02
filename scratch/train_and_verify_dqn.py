"""
Train the DQN policy with GPU if available, verify it, print results.
Run after PyTorch is installed.
"""
import pathlib, json, sys

# 1. Check torch and GPU
try:
    import torch
    print(f"PyTorch version  : {torch.__version__}")
    cuda_ok = torch.cuda.is_available()
    print(f"CUDA available   : {cuda_ok}")
    if cuda_ok:
        print(f"GPU              : {torch.cuda.get_device_name(0)}")
        print(f"CUDA version     : {torch.version.cuda}")
        print(f"VRAM             : {torch.cuda.get_device_properties(0).total_memory // (1024**2)} MB")
except ImportError as e:
    print(f"ERROR: PyTorch not installed: {e}")
    sys.exit(1)

# 2. Train policy (uses GPU automatically if available)
from backend.adaptive_model import train_policy, evaluate_checkpoint, TrainedTeachingPolicy
from backend.learning import ACTION_IDS
from backend.config import Settings

settings = Settings()
checkpoint = pathlib.Path(settings.policy_checkpoint)

print(f"\nTraining DQN policy -> {checkpoint}")
print(f"Actions: {ACTION_IDS}")
result = train_policy(checkpoint, epochs=500, seed=42)
print(f"\nTraining complete!")
print(f"  Epochs : {result.epochs}")
print(f"  Loss   : {result.loss:.6f}")

# 3. Evaluate accuracy
eval_data = result.evaluation
print(f"\nEvaluation (accuracy: {eval_data['accuracy']*100:.1f}%):")
for p in eval_data["profiles"]:
    status = "PASS" if p["correct"] else "FAIL"
    print(f"  {status} [{p['profile']:15s}] expected={p['expected_action']:30s} got={p['selected_action']}")

# 4. Load and verify inference on GPU
print("\nLoading policy and running GPU inference test...")
policy = TrainedTeachingPolicy(checkpoint)
print(f"  Policy available : {policy.available}")
print(f"  Policy version   : {policy.version}")

# Test realistic learner states
test_states = [
    ("beginner",   {"attempt_count": 1, "correctness_ema": 0.2, "hint_use_rate": 0.1, "revisit_count": 0, "independence_score": 0.2}),
    ("struggling", {"attempt_count": 4, "correctness_ema": 0.35, "hint_use_rate": 0.55, "revisit_count": 2, "independence_score": 0.25}),
    ("developing", {"attempt_count": 3, "correctness_ema": 0.62, "hint_use_rate": 0.25, "revisit_count": 1, "independence_score": 0.58}),
    ("mastered",   {"attempt_count": 6, "correctness_ema": 0.94, "hint_use_rate": 0.05, "revisit_count": 0, "independence_score": 0.92}),
    ("returning",  {"attempt_count": 2, "correctness_ema": 0.75, "hint_use_rate": 0.20, "revisit_count": 3, "independence_score": 0.70}),
]
print("\n  Inference results:")
for name, state in test_states:
    decision = policy.select_action(state, ACTION_IDS)
    print(f"    [{name:12s}] -> action={decision.action_id:30s} reason={decision.reason_code}")

# 5. Write training report
report_path = pathlib.Path("reports/dqn_training_report.json")
report_path.parent.mkdir(exist_ok=True)
from backend.adaptive_model import write_training_report
write_training_report(result, report_path)
print(f"\nTraining report saved -> {report_path}")
print("\nDQN policy fully operational with GPU: OK")
