from backend.adaptive_model import train_policy, write_training_report
from backend.config import Settings


def main() -> None:
    settings = Settings()
    checkpoint = settings.storage_dir / "models" / "teaching_policy.pt"
    result = train_policy(checkpoint)
    report = settings.storage_dir / "models" / "teaching_policy-evaluation.json"
    write_training_report(result, report)
    print(report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
