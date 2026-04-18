# Verify all configured adapters can connect before running the pipeline
# Usage: python scripts/test_adapters.py

from dotenv import load_dotenv
load_dotenv()

from config.registry import load_adapters


def check():
    adapters = load_adapters()
    results = {}

    for name, adapter in adapters.items():
        try:
            adapter.health_check()
            results[name] = "OK"
        except Exception as e:
            results[name] = f"FAILED — {e}"

    for name, status in results.items():
        print(f"  {name}: {status}")

    if any("FAILED" in s for s in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    check()
