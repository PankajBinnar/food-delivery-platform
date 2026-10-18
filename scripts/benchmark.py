
import csv
import os
import statistics
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"
RESTAURANT_ID = int(os.getenv("RESTAURANT_ID", "1"))
REQUEST_COUNT = int(os.getenv("REQUEST_COUNT", "200"))
WARMUP_COUNT = 10

url = f"{BASE_URL}/restaurants/{RESTAURANT_ID}/menu"

print(f"Benchmark URL: {url}")
print(f"Measured requests: {REQUEST_COUNT}")
print("Warming up the API...")

# Warm up the server and database connection pool.
for _ in range(WARMUP_COUNT):
    response = requests.get(url, timeout=10)
    response.raise_for_status()

latencies_ms = []
errors = 0

print("Starting benchmark...")

for i in range(REQUEST_COUNT):
    start = time.perf_counter()

    try:
        response = requests.get(url, timeout=15)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            latencies_ms.append(elapsed_ms)
        else:
            errors += 1
            print(f"Request {i + 1}: HTTP {response.status_code}")

    except requests.RequestException as exc:
        errors += 1
        print(f"Request {i + 1} failed: {exc}")

if not latencies_ms:
    raise SystemExit("No successful requests. Check FastAPI and the URL.")

ordered = sorted(latencies_ms)

def percentile(values, percentile_value):
    index = round((len(values) - 1) * percentile_value / 100)
    return values[index]

total_seconds = sum(latencies_ms) / 1000

print("\n===== BASELINE RESULTS =====")
print(f"Successful requests: {len(latencies_ms)}")
print(f"Failed requests:     {errors}")
print(f"Average latency:     {statistics.mean(latencies_ms):.2f} ms")
print(f"Median (p50):        {statistics.median(latencies_ms):.2f} ms")
print(f"p95 latency:         {percentile(ordered, 95):.2f} ms")
print(f"Maximum latency:     {max(latencies_ms):.2f} ms")
print(f"Throughput:          {len(latencies_ms) / total_seconds:.2f} requests/sec")

output_file = Path(__file__).resolve().parent / "baseline_before_redis.csv"

with output_file.open("w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["request_number", "latency_ms"])

    for number, latency in enumerate(latencies_ms, start=1):
        writer.writerow([number, round(latency, 3)])

print(f"\nIndividual results saved to: {output_file}")
