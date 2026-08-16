from __future__ import annotations

import pytest

from pricing_engine.ml.generate_sales_history import generate_sales_history
from pricing_engine.ml.train import BASELINE_IMPROVEMENT_THRESHOLD, train_and_evaluate


@pytest.mark.slow
class TestTrainAndEvaluate:
    def test_model_beats_naive_baseline_on_holdout(self):
        df = generate_sales_history(flights_per_route=20)

        result = train_and_evaluate(df)

        assert result.model_mae <= result.baseline_mae * BASELINE_IMPROVEMENT_THRESHOLD
        assert result.beats_baseline
