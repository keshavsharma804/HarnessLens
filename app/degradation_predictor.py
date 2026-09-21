"""
Predicts orchestrator degradation and recommends intervention.

Reads the EntropyMonitor's history and produces a single recommendation.
The recommendation maps to a concrete action the control plane can take.
"""

from dataclasses import dataclass

from app.entropy_monitor import EntropyMonitor


@dataclass
class Prediction:
    should_intervene: bool
    intervention_type: str     # "none" | "compress_context" | "switch_orchestrator" | "abort"
    steps_until_failure: int
    detail: str


class DegradationPredictor:
    def __init__(self, monitor: EntropyMonitor):
        self.monitor = monitor

    def predict(self) -> Prediction:
        if not self.monitor.history:
            return Prediction(
                should_intervene=False,
                intervention_type="none",
                steps_until_failure=-1,
                detail="No history yet.",
            )

        trend = self.monitor.trend()
        steps = self.monitor.predict_failure_in_steps()
        latest = self.monitor.latest()

        if latest.prediction == "critical":
            return Prediction(
                should_intervene=True,
                intervention_type="abort",
                steps_until_failure=0,
                detail="Orchestrator critical. Abort or escalate to human.",
            )

        if latest.prediction == "warning" and trend == "rising":
            if 0 <= steps <= 3:
                return Prediction(
                    should_intervene=True,
                    intervention_type="switch_orchestrator",
                    steps_until_failure=steps,
                    detail=f"Switch orchestrator in ~{steps} steps.",
                )
            return Prediction(
                should_intervene=True,
                intervention_type="compress_context",
                steps_until_failure=steps,
                detail="Compress context to reduce entropy.",
            )

        return Prediction(
            should_intervene=False,
            intervention_type="none",
            steps_until_failure=steps,
            detail=f"Trend: {trend}.",
        )