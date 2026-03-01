import os

import openmeteo_requests
import requests_cache
import pandas as pd
from pandas import DataFrame
from retry_requests import retry
from dotenv import load_dotenv

load_dotenv()

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS


from datetime import datetime, timedelta

def get_hourly_weather_records_by_date(
    start_date: str, end_date: str, lat: float = 42.8162, long: float = -108.7019
) -> DataFrame:
    cache_session = requests_cache.CachedSession(".cache", expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": long,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "rain",
            "visibility",
            "wind_speed_10m",
            "snowfall",
            "snow_depth",
            "soil_temperature_0cm",
            "cloud_cover",
            "cloud_cover_low",
            "cloud_cover_mid",
            "cloud_cover_high",
        ],
        "timezone": "America/Denver",
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]
    hourly = response.Hourly()
    hourly_data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        ),
        "temperature_2m": hourly.Variables(0).ValuesAsNumpy(),
        "relative_humidity_2m": hourly.Variables(1).ValuesAsNumpy(),
        "precipitation": hourly.Variables(2).ValuesAsNumpy(),
        "rain": hourly.Variables(3).ValuesAsNumpy(),
        "visibility": hourly.Variables(4).ValuesAsNumpy(),
        "wind_speed_10m": hourly.Variables(5).ValuesAsNumpy(),
        "snowfall": hourly.Variables(6).ValuesAsNumpy(),
        "snow_depth": hourly.Variables(7).ValuesAsNumpy(),
        "soil_temperature_0cm": hourly.Variables(8).ValuesAsNumpy(),
        "cloud_cover": hourly.Variables(9).ValuesAsNumpy(),
        "cloud_cover_low": hourly.Variables(10).ValuesAsNumpy(),
        "cloud_cover_mid": hourly.Variables(11).ValuesAsNumpy(),
        "cloud_cover_high": hourly.Variables(12).ValuesAsNumpy(),
    }

    return pd.DataFrame(data=hourly_data)


def get_latest_timestamp(location_name: str) -> pd.Timestamp:
    client = InfluxDBClient(
        url=os.getenv("INFLUXDB_URL"),
        token=os.getenv("INFLUXDB_TOKEN"),
        org=os.getenv("INFLUXDB_ORG"),
    )
    query_api = client.query_api()
    query = f'from(bucket: "{os.getenv("INFLUXDB_BUCKET")}") \
        |> range(start: 0) \
        |> filter(fn: (r) => r["_measurement"] == "hourly_weather") \
        |> filter(fn: (r) => r["location"] == "{location_name}") \
        |> last()'
    tables = query_api.query(query)
    if not tables:
        return None
    return tables[0].records[0].get_time()


def get_global_latest_timestamp() -> pd.Timestamp:
    client = InfluxDBClient(
        url=os.getenv("INFLUXDB_URL"),
        token=os.getenv("INFLUXDB_TOKEN"),
        org=os.getenv("INFLUXDB_ORG"),
    )
    query_api = client.query_api()
    query = f'from(bucket: "{os.getenv("INFLUXDB_BUCKET")}") \
        |> range(start: -365d) \
        |> filter(fn: (r) => r["_measurement"] == "hourly_weather") \
        |> group() \
        |> max(column: "_time")'
    tables = query_api.query(query)
    if not tables or not tables[0].records:
        return None
    return pd.Timestamp(tables[0].records[0].get_time())


def insert_hourly_weather_records(records: pd.DataFrame, location_name: str):
    latest_timestamp = get_latest_timestamp(location_name)

    if latest_timestamp:
        records = records[records["date"] > latest_timestamp]

    if records.empty:
        print(f"No new records to insert for {location_name}.")
        return

    client = InfluxDBClient(
        url=os.getenv("INFLUXDB_URL"),
        token=os.getenv("INFLUXDB_TOKEN"),
        org=os.getenv("INFLUXDB_ORG"),
    )
    write_api = client.write_api(write_options=ASYNCHRONOUS)

    for row in records.itertuples(index=False):
      # SQL data preparation
      date = pd.to_datetime(getattr(row, "date")).to_pydatetime()
      temp = getattr(row, "temperature_2m")
      precip = getattr(row, "precipitation")
      wind = getattr(row, "wind_speed_10m")

      # InfluxDB data preparation and write
      point = (
          Point("hourly_weather")
          .tag("location", location_name)
          .field("temperature", float(temp))
          .field("relative_humidity", float(getattr(row, "relative_humidity_2m")))
          .field("precipitation", float(precip))
          .field("rain", float(getattr(row, "rain")))
          .field("visibility", float(getattr(row, "visibility")))
          .field("wind_speed", float(wind))
          .field("snowfall", float(getattr(row, "snowfall")))
          .field("snow_depth", float(getattr(row, "snow_depth")))
          .field("soil_temperature", float(getattr(row, "soil_temperature_0cm")))
          .field("cloud_cover", float(getattr(row, "cloud_cover")))
          .field("cloud_cover_low", float(getattr(row, "cloud_cover_low")))
          .field("cloud_cover_mid", float(getattr(row, "cloud_cover_mid")))
          .field("cloud_cover_high", float(getattr(row, "cloud_cover_high")))
          .time(date)
      )
      write_api.write(bucket=os.getenv("INFLUXDB_BUCKET"), record=point)

if __name__ == "__main__":
    # Determine start_date from InfluxDB
    latest_ts = get_global_latest_timestamp()
    if latest_ts:
        # Start from the day of the latest record to ensure we don't miss any hours in that day
        start_date = latest_ts.strftime("%Y-%m-%d")
        print(f"Latest record found: {latest_ts}. Setting start_date to {start_date}")
    else:
        # Default fallback if bucket is empty
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        print(f"No records found. Defaulting start_date to {start_date}")

    # End date is today
    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"End date set to: {end_date}")

    # Lander hourly records
    lander_hourly_weather_records = get_hourly_weather_records_by_date(
        start_date, end_date, lat=42.8162, long=-108.7019
    )
    insert_hourly_weather_records(lander_hourly_weather_records, location_name="lander")

    # Pinedale hourly records
    pinedale_hourly_weather_records = get_hourly_weather_records_by_date(
        start_date, end_date, lat=42.8666, long=-109.861
    )
    insert_hourly_weather_records(
        pinedale_hourly_weather_records, location_name="pinedale"
    )

    # Dubois hourly records
    dubois_hourly_weather_records = get_hourly_weather_records_by_date(
        start_date, end_date, lat=43.5336, long=-109.6304
    )
    insert_hourly_weather_records(
        dubois_hourly_weather_records, location_name="dubois"
    )
