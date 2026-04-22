"""Track token usage and cost per model across a scraping session."""
import logging
from app.config import MODEL_PRICING

logger = logging.getLogger(__name__)


class CostTracker:
    def __init__(self):
        self._data: dict[str, dict] = {}

    def log(self, model_id: str, response) -> None:
        """Log a completed LLM call's token usage."""
        usage = response.usage
        if model_id not in self._data:
            self._data[model_id] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }

        pricing = MODEL_PRICING.get(model_id, {"input": 0.0, "output": 0.0})
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        cost = (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

        self._data[model_id]["calls"] += 1
        self._data[model_id]["input_tokens"] += input_tokens
        self._data[model_id]["output_tokens"] += output_tokens
        self._data[model_id]["cost_usd"] += cost

    def get_cost(self) -> dict:
        """Return full cost breakdown plus total."""
        breakdown = {}
        total = 0.0

        for model_id, data in self._data.items():
            breakdown[model_id] = {
                "calls": data["calls"],
                "input_tokens": data["input_tokens"],
                "output_tokens": data["output_tokens"],
                "cost_usd": round(data["cost_usd"], 6),
            }
            total += data["cost_usd"]

        return {"breakdown": breakdown, "total_usd": round(total, 6)}

    def print_summary(self) -> None:
        cost = self.get_cost()
        print("\n── Cost Summary ──────────────────────────────")
        for model_id, data in cost["breakdown"].items():
            print(
                f"  {model_id}: {data['calls']} calls | "
                f"{data['input_tokens']} in / {data['output_tokens']} out | "
                f"${data['cost_usd']:.6f}"
            )
        print(f"  TOTAL: ${cost['total_usd']:.6f}")
        print("──────────────────────────────────────────────\n")
