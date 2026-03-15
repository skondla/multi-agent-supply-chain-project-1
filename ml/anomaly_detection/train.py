"""MLOps: Anomaly detection model training (Isolation Forest)."""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def generate_synthetic_transactions(n_normal: int = 10000, n_anomalies: int = 500) -> pd.DataFrame:
    """Generate synthetic transaction data with labeled anomalies."""
    normal = pd.DataFrame({
        "order_amount": np.random.lognormal(4.0, 0.8, n_normal),
        "quantity": np.random.randint(1, 20, n_normal),
        "hour_of_day": np.random.randint(6, 22, n_normal),
        "day_of_week": np.random.randint(0, 7, n_normal),
        "customer_order_count": np.random.poisson(5, n_normal) + 1,
        "time_since_last_order_hours": np.random.exponential(72, n_normal),
        "items_in_cart": np.random.randint(1, 10, n_normal),
        "is_international": np.random.binomial(1, 0.1, n_normal),
        "payment_method_encoded": np.random.randint(0, 4, n_normal),
        "is_anomaly": 0,
    })
    anomalies = pd.DataFrame({
        "order_amount": np.random.lognormal(7.0, 1.5, n_anomalies),
        "quantity": np.random.randint(100, 1000, n_anomalies),
        "hour_of_day": np.random.choice([1, 2, 3, 4], n_anomalies),
        "day_of_week": np.random.randint(0, 7, n_anomalies),
        "customer_order_count": np.ones(n_anomalies, dtype=int),
        "time_since_last_order_hours": np.random.exponential(1, n_anomalies),
        "items_in_cart": np.random.randint(20, 100, n_anomalies),
        "is_international": np.random.binomial(1, 0.8, n_anomalies),
        "payment_method_encoded": np.random.randint(0, 4, n_anomalies),
        "is_anomaly": 1,
    })
    return pd.concat([normal, anomalies], ignore_index=True).sample(frac=1, random_state=42)


def train_anomaly_model(args: argparse.Namespace) -> None:
    """Train and register anomaly detection model."""
    mlflow.set_tracking_uri(args.mlflow_tracking_uri)
    mlflow.set_experiment("anomaly-detection")

    with mlflow.start_run(run_name=f"isolation-forest-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}") as run:
        print(f"MLflow Run ID: {run.info.run_id}")

        mlflow.log_params({
            "n_estimators": args.n_estimators,
            "contamination": args.contamination,
            "max_samples": args.max_samples,
        })

        print("Loading training data...")
        df = generate_synthetic_transactions(n_normal=50000, n_anomalies=2500)

        feature_cols = [
            "order_amount", "quantity", "hour_of_day", "day_of_week",
            "customer_order_count", "time_since_last_order_hours",
            "items_in_cart", "is_international", "payment_method_encoded",
        ]
        X, y = df[feature_cols], df["is_anomaly"]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        print("Training Isolation Forest...")
        model = IsolationForest(
            n_estimators=args.n_estimators,
            contamination=args.contamination,
            max_samples=args.max_samples,
            random_state=42, n_jobs=-1,
        )
        model.fit(X_train_scaled)

        y_pred = (model.predict(X_test_scaled) == -1).astype(int)
        y_scores = -model.score_samples(X_test_scaled)

        f1 = f1_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred)
        try:
            roc_auc = roc_auc_score(y_test, y_scores)
        except Exception:
            roc_auc = 0.0

        mlflow.log_metrics({"f1_score": f1, "precision": precision, "recall": recall, "roc_auc": roc_auc})
        print(f"\nF1={f1:.4f} Precision={precision:.4f} Recall={recall:.4f} ROC-AUC={roc_auc:.4f}")
        print(classification_report(y_test, y_pred, target_names=["normal", "anomaly"]))

        if f1 >= args.f1_threshold:
            print(f"F1 {f1:.4f} >= threshold {args.f1_threshold}. Registering...")
            with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
                pickle.dump(scaler, f)
                mlflow.log_artifact(f.name, "scaler")
            mlflow.sklearn.log_model(model, artifact_path="model", registered_model_name="anomaly-detection")
            mlflow.log_dict({"feature_cols": feature_cols}, "feature_config.json")
            print("Model registered as 'anomaly-detection'")
        else:
            print(f"F1 {f1:.4f} < threshold {args.f1_threshold}. NOT registered.")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Train anomaly detection model")
    parser.add_argument("--mlflow-tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--contamination", type=float, default=0.05)
    parser.add_argument("--max-samples", default="auto")
    parser.add_argument("--f1-threshold", type=float, default=0.80)
    train_anomaly_model(parser.parse_args())


if __name__ == "__main__":
    main()
