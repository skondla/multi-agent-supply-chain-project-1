"""MLOps: Demand forecasting model training with MLflow tracking."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def generate_synthetic_data(n_days: int = 365, n_products: int = 50) -> pd.DataFrame:
    """Generate synthetic demand data (replace with DB query in production)."""
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n_days, freq="D")
    records = []
    for product_id in range(n_products):
        base_demand = np.random.randint(50, 500)
        seasonal_amplitude = np.random.uniform(0.1, 0.3)
        trend = np.random.uniform(-0.001, 0.003)
        for i, date in enumerate(dates):
            weekly_season = np.sin(2 * np.pi * date.dayofweek / 7) * 0.15
            annual_season = np.sin(2 * np.pi * date.dayofyear / 365) * seasonal_amplitude
            demand = base_demand * (1 + weekly_season + annual_season + trend * i + np.random.normal(0, 0.05))
            records.append({
                "product_id": f"PROD-{product_id:04d}",
                "date": date,
                "demand": max(0, int(demand)),
                "day_of_week": date.dayofweek,
                "day_of_month": date.day,
                "month": date.month,
                "quarter": date.quarter,
                "is_weekend": int(date.dayofweek >= 5),
                "week_of_year": date.isocalendar()[1],
                "year": date.year,
            })
    return pd.DataFrame(records)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag and rolling features for time series forecasting."""
    df = df.sort_values(["product_id", "date"]).copy()
    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}"] = df.groupby("product_id")["demand"].shift(lag)
    for window in [7, 28]:
        df[f"demand_rolling_mean_{window}"] = (
            df.groupby("product_id")["demand"]
            .transform(lambda x: x.shift(1).rolling(window).mean())
        )
        df[f"demand_rolling_std_{window}"] = (
            df.groupby("product_id")["demand"]
            .transform(lambda x: x.shift(1).rolling(window).std())
        )
    df["product_idx"] = df["product_id"].astype("category").cat.codes
    return df.dropna()


def train_model(args: argparse.Namespace) -> None:
    """Train XGBoost demand forecasting model."""
    mlflow.set_tracking_uri(args.mlflow_tracking_uri)
    mlflow.set_experiment("demand-forecast")

    with mlflow.start_run(run_name=f"xgboost-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}") as run:
        print(f"MLflow Run ID: {run.info.run_id}")

        params = {
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "learning_rate": args.learning_rate,
            "subsample": args.subsample,
            "colsample_bytree": args.colsample_bytree,
        }
        mlflow.log_params(params)

        print("Loading training data...")
        df = generate_synthetic_data(n_days=730, n_products=100)
        df = engineer_features(df)

        feature_cols = [
            "day_of_week", "day_of_month", "month", "quarter",
            "is_weekend", "week_of_year", "year", "product_idx",
        ] + [c for c in df.columns if "lag_" in c or "rolling_" in c]

        X, y = df[feature_cols], df["demand"]
        tscv = TimeSeriesSplit(n_splits=args.n_splits)
        cv_mapes = []
        best_model, best_mape = None, float("inf")

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model = xgb.XGBRegressor(
                n_estimators=args.n_estimators, max_depth=args.max_depth,
                learning_rate=args.learning_rate, subsample=args.subsample,
                colsample_bytree=args.colsample_bytree,
                objective="reg:squarederror", random_state=42, n_jobs=-1,
                early_stopping_rounds=50,
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            mape = mean_absolute_percentage_error(y_val, model.predict(X_val))
            cv_mapes.append(mape)
            print(f"Fold {fold+1}: MAPE={mape:.4f}")
            if mape < best_mape:
                best_mape, best_model = mape, model

        avg_mape = float(np.mean(cv_mapes))
        mlflow.log_metrics({"cv_mape_mean": avg_mape, "cv_mape_std": float(np.std(cv_mapes)), "mape": avg_mape})
        print(f"\nCV MAPE: {avg_mape:.4f} (threshold: {args.mape_threshold})")

        if avg_mape <= args.mape_threshold:
            mlflow.xgboost.log_model(best_model, artifact_path="model", registered_model_name="demand-forecast")
            print("Model registered as 'demand-forecast'")
        else:
            print(f"MAPE {avg_mape:.4f} exceeds threshold {args.mape_threshold}. NOT registered.")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Train demand forecasting model")
    parser.add_argument("--mlflow-tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--subsample", type=float, default=0.8)
    parser.add_argument("--colsample-bytree", type=float, default=0.8)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--mape-threshold", type=float, default=0.15)
    train_model(parser.parse_args())


if __name__ == "__main__":
    main()
