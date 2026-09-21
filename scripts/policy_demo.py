import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.policy_signer import default_signer
from app.behavior_gate import default_gate


def main():
    print("\n=== Scenario 1: Policy signature ===\n")
    path = "policies/default.yaml"
    sig = default_signer.sign_file(path)
    print(f"  Policy: {path}")
    print(f"  Signature: {sig[:32]}...")
    print(f"  Verify with same signature: {default_signer.verify_file(path, sig)}")
    print(f"  Verify with wrong signature: {default_signer.verify_file(path, 'deadbeef')}")

    print("\n=== Scenario 2: Behavior gate ===\n")
    cases = [
        {"tool_name": "write_file", "risk_level": "high"},
        {"tool_name": "run_command", "target_environment": "production"},
        {"tool_name": "read_file", "path": "/app/.env"},
        {"tool_name": "read_file", "path": "/app/readme.md"},
    ]
    for ctx in cases:
        decision = default_gate.evaluate(ctx)
        print(f"  {ctx}")
        print(f"    -> {decision.verdict.upper()} ({decision.rule_name})")
        print(f"    reason: {decision.reason}")


if __name__ == "__main__":
    main()