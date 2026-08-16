from __future__ import annotations

from pricing_engine.experimentation import assignment
from pricing_engine.experimentation.assignment import assign_variant, is_experiment_active

EXPERIMENT_ID = "demand_elasticity_v1"


class TestAssignVariant:
    def test_same_customer_and_experiment_always_same_variant(self):
        first = assign_variant("customer-42", EXPERIMENT_ID, 0.5)
        second = assign_variant("customer-42", EXPERIMENT_ID, 0.5)

        assert first == second

    def test_split_ratio_respected_within_tolerance(self):
        customer_ids = [f"customer-{i}" for i in range(1000)]
        treatment_count = sum(
            1 for c in customer_ids if assign_variant(c, EXPERIMENT_ID, 0.5) == "treatment"
        )

        assert 400 <= treatment_count <= 600

    def test_split_zero_always_control(self):
        customer_ids = [f"customer-{i}" for i in range(100)]

        assert all(assign_variant(c, EXPERIMENT_ID, 0.0) == "control" for c in customer_ids)

    def test_split_one_always_treatment(self):
        customer_ids = [f"customer-{i}" for i in range(100)]

        assert all(assign_variant(c, EXPERIMENT_ID, 1.0) == "treatment" for c in customer_ids)

    def test_variant_is_a_function_of_experiment_id_too(self):
        # Not asserting inequality (could coincidentally match for a given
        # customer_id) — just that the function actually consumes
        # experiment_id rather than ignoring it, checked across many ids.
        customer_ids = [f"customer-{i}" for i in range(200)]
        same_experiment = [assign_variant(c, "exp-a", 0.5) for c in customer_ids]
        other_experiment = [assign_variant(c, "exp-b", 0.5) for c in customer_ids]

        assert same_experiment != other_experiment


class TestIsExperimentActive:
    def test_false_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(assignment, "ENABLE_ML_PRICING", False)

        assert is_experiment_active() is False

    def test_false_when_flag_on_but_no_model_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(assignment, "ENABLE_ML_PRICING", True)
        monkeypatch.setattr(assignment, "DEMAND_MODEL_PATH", str(tmp_path / "missing.joblib"))

        assert is_experiment_active() is False

    def test_true_when_flag_on_and_model_file_exists(self, monkeypatch, tmp_path):
        model_path = tmp_path / "model.joblib"
        model_path.write_text("stub")
        monkeypatch.setattr(assignment, "ENABLE_ML_PRICING", True)
        monkeypatch.setattr(assignment, "DEMAND_MODEL_PATH", str(model_path))

        assert is_experiment_active() is True
