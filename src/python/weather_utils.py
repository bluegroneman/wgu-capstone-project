import os
import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def fetch_influx_data(bucket="OpenMeteo", range_start="-365d"):
    """Fetches and pivots weather data from InfluxDB."""
    client = InfluxDBClient(
        url=os.getenv("INFLUXDB_URL"),
        token=os.getenv("INFLUXDB_TOKEN"),
        org=os.getenv("INFLUXDB_ORG"),
    )
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {range_start})
      |> filter(fn: (r) => r["_measurement"] == "hourly_weather")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    # Query returns a list of dataframes if there are multiple tables
    df_list = query_api.query_data_frame(query)
    if isinstance(df_list, list):
        df = pd.concat(df_list)
    else:
        df = df_list

    # Cleanup columns
    cols_to_drop = ["result", "table", "_start", "_stop", "_measurement"]
    df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

    # Set time as index
    df["_time"] = pd.to_datetime(df["_time"])
    df = df.rename(columns={"_time": "time"})
    df = df.sort_values(["location", "time"])

    return df


def engineer_features(df):
    """Creates lags, rolling statistics, and temporal features."""
    # Create a copy to avoid SettingWithCopyWarning
    df = df.copy()

    # 1. Temporal Features
    df["hour"] = df["time"].dt.hour
    df["day_of_year"] = df["time"].dt.dayofyear
    df["month"] = df["time"].dt.month

    # Periodic encoding for cyclical features
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    # 2. Lagged Features (per location)
    lags = [1, 3, 6, 24]
    features_to_lag = [
        "temperature",
        "precipitation",
        "wind_speed",
        "relative_humidity",
        "cloud_cover",
        "rain",
        "snowfall",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "rain",
        "precipitation",
        "snowfall",
    ]

    for lag in lags:
        for col in features_to_lag:
            if col in df.columns:
                df[f"{col}_lag_{lag}"] = df.groupby("location")[col].shift(lag)

    # 3. Rolling Statistics (per location)
    windows = [6, 24]
    for window in windows:
        for col in features_to_lag:
            if col in df.columns:
                df[f"{col}_roll_mean_{window}"] = df.groupby("location")[col].transform(
                    lambda x: x.rolling(window).mean()
                )
                df[f"{col}_roll_std_{window}"] = df.groupby("location")[col].transform(
                    lambda x: x.rolling(window).std()
                )

    # Handle missing values created by lags/rolling windows
    df = df.dropna()

    return df
