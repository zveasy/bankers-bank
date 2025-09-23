#!/usr/bin/env python3
"""Script to identify failing tests."""
import subprocess
import sys

def run_tests():
    """Run pytest and capture failing tests."""
    cmd = [sys.executable, "-m", "pytest", "--tb=no", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")

    if result.returncode == 0:
        print("✅ All tests passed!")
        return

    print("❌ Failing tests found:")
    print("=" * 50)

    # Parse the output to find failed tests
    lines = result.stdout.split('\n')
    failed_tests = []

    for line in lines:
        if 'FAILED' in line and '.py::' in line:
            test_name = line.split('FAILED')[0].strip()
            if test_name:
                failed_tests.append(test_name)

    if failed_tests:
        for i, test in enumerate(failed_tests, 1):
            print(f"{i:2d}. {test}")
    else:
        print("Could not parse failing tests from output")

if __name__ == "__main__":
    run_tests()
