import subprocess
import sys
from pathlib import Path


def run_all_tests():
  test_files = [
    "tests/config/test_settings.py",
    "tests/core/test_models.py",
    "tests/core/test_funding.py",
    "tests/core/test_risk.py",
    "tests/core/test_spread.py",
    "tests/exchanges/test_gate.py",
    "tests/exchanges/test_hyperliquid.py",
    "tests/strategy/test_arbitrage.py",
    "tests/utils/test_logging.py",
  ]
  
  results = {}
  failed = []
  
  for test_file in test_files:
    print(f"\n{'=' * 80}")
    print(f"Running: {test_file}")
    print('=' * 80)
    
    result = subprocess.run(
      ["pytest", test_file, "-v", "--tb=short"],
      capture_output=False
    )
    
    results[test_file] = result.returncode
    
    if result.returncode != 0:
      failed.append(test_file)
  
  print(f"\n{'=' * 80}")
  print("SUMMARY")
  print('=' * 80)
  
  for test_file, code in results.items():
    status = "✓ PASS" if code == 0 else "✗ FAIL"
    print(f"{status} - {test_file}")
  
  if failed:
    print(f"\n{len(failed)} test file(s) failed:")
    for f in failed:
      print(f"  - {f}")
    sys.exit(1)
  else:
    print("\n✓ All tests passed!")
    sys.exit(0)


def run_with_coverage():
  print("Running tests with coverage...")
  
  result = subprocess.run([
    "pytest",
    "tests/",
    "-v",
    "--tb=short",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html"
  ])
  
  if result.returncode == 0:
    print("\n✓ All tests passed!")
    print("Coverage report generated in htmlcov/index.html")
  else:
    print("\n✗ Some tests failed")
  
  sys.exit(result.returncode)


if __name__ == "__main__":
  if len(sys.argv) > 1 and sys.argv[1] == "--coverage":
    run_with_coverage()
  else:
    run_all_tests()