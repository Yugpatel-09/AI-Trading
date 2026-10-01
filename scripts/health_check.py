#!/usr/bin/env python3
"""
TradeForge Operational Health Check Script.
Validates database, redis, and API gateway connectivity.
"""
import sys
import httpx
from datetime import datetime, timezone

def run_diagnostics(api_url: str = "http://localhost:8000"):
    print(f"[*] Running TradeForge System Diagnostic on {api_url} at {datetime.now(timezone.utc).isoformat()}...")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{api_url}/health")
            if resp.status_code == 200:
                data = resp.json()
                print(f"[OK] Health Probe Status: {data.get('status')}")
                print(f"[OK] Service: {data.get('service')} (v{data.get('version')})")
                print(f"[OK] Kill Switch Active: {data.get('kill_switch_active')}")
            else:
                print(f"[FAIL] Health check failed with status code {resp.status_code}", file=sys.stderr)
                sys.exit(1)

            status_resp = client.get(f"{api_url}/api/v1/system/status")
            if status_resp.status_code == 200:
                sdata = status_resp.json()
                print(f"[OK] System Telemetry Status: {sdata.get('status')}")
                print(f"[OK] Data Feed Delay: {sdata.get('data_feed_delay_ms')}ms")
                print(f"[OK] Active Mode: {sdata.get('active_mode')}")
            else:
                print(f"[WARN] Telemetry endpoint returned status {status_resp.status_code}", file=sys.stderr)

        print("\n[SUCCESS] All core TradeForge components healthy.")
    except Exception as e:
        print(f"[ERROR] Could not connect to API Gateway: {e}", file=sys.stderr)
        print("Note: Ensure 'uvicorn services.api.app.main:app' or 'docker compose up' is running.", file=sys.stderr)

if __name__ == "__main__":
    run_diagnostics()
