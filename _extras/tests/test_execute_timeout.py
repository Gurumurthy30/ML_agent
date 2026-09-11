"""
tests/test_execute_timeout.py — Timeout enforcement test for execute_code MCP tool

Confirms that running code which hangs (e.g., time.sleep(999)) triggers
subprocess.TimeoutExpired, returning a structured dict with:
- status == "timeout"
- error containing "Timeout"
- cv_mean == 0.0, cv_std == 0.0
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.local_env_mcp.server import LocalEnvMCP


def test_execute_code_timeout():
    # Instantiate with a 2-second timeout for quick test execution
    mcp = LocalEnvMCP(session_id="test_timeout_sess", exec_timeout=2, dry_run=False)

    hang_code = """
import time
print("Starting long sleep...")
time.sleep(30)
print("Should never reach here")
"""
    print("[Test] Executing hanging code with exec_timeout=2s...")
    result = mcp.execute_code(hang_code)
    print(f"[Test] Result received: {result}")

    assert result["status"] == "timeout", f"Expected status 'timeout', got '{result.get('status')}'"
    assert "Timeout" in result.get("error", "") or "timed out" in result.get("error", "").lower(), (
        f"Expected 'Timeout' in error, got: {result.get('error')}"
    )
    assert result.get("cv_mean") == 0.0, f"Expected cv_mean == 0.0, got {result.get('cv_mean')}"
    assert result.get("cv_std") == 0.0, f"Expected cv_std == 0.0, got {result.get('cv_std')}"
    print("[PASS] Timeout test passed successfully!")


if __name__ == "__main__":
    test_execute_code_timeout()
