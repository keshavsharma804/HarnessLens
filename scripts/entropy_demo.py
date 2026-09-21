import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.entropy_monitor import EntropyMonitor
from app.degradation_predictor import DegradationPredictor


def main():
    print("\n=== Scenario: Orchestrator degrading over a long trajectory ===\n")

    monitor = EntropyMonitor(window=10, warning_threshold=0.6, critical_threshold=0.8)
    predictor = DegradationPredictor(monitor)

    # Simulate a trajectory where decisions become increasingly uncertain
    # as context accumulates.
    trajectory = [
        # step,  decision_scores,             context_size
        (1,  {"researchharness": 0.90, "easyloops": 0.10},  500),
        (2,  {"researchharness": 0.85, "easyloops": 0.15},  1200),
        (3,  {"researchharness": 0.75, "easyloops": 0.25},  2500),
        (4,  {"researchharness": 0.65, "easyloops": 0.35},  4000),
        (5,  {"researchharness": 0.55, "easyloops": 0.45},  5500),
        (6,  {"researchharness": 0.50, "easyloops": 0.50},  7000),
        (7,  {"researchharness": 0.48, "easyloops": 0.52},  8500),
        (8,  {"researchharness": 0.45, "easyloops": 0.55},  9500),
    ]

    for step, scores, ctx in trajectory:
        snap = monitor.record(step, scores, context_size=ctx)
        pred = predictor.predict()
        marker = ""
        if pred.should_intervene:
            marker = f"  <<< INTERVENE: {pred.intervention_type}"
        print(
            f"  step={step}  "
            f"entropy={snap.entropy:.3f}  "
            f"prediction={snap.prediction:8s}  "
            f"trend={monitor.trend():17s}"
            f"{marker}"
        )

    print("\n=== Final prediction ===\n")
    pred = predictor.predict()
    print(f"  should_intervene: {pred.should_intervene}")
    print(f"  intervention_type: {pred.intervention_type}")
    print(f"  steps_until_failure: {pred.steps_until_failure}")
    print(f"  detail: {pred.detail}")


if __name__ == "__main__":
    main()