"""Device resolution and capability validation.

Loads device specs from YAML primitives and probes runtime capabilities.
- resolve_device(): Load device spec from path or short name
- validate_capabilities(): Probe runtime PMU/osnoise availability
"""
import copy
import json
import platform
import subprocess
from pathlib import Path
from typing import Optional

import yaml


DEVICES_DIR = Path("primitives/devices")


def resolve_device(device_arg: Optional[str] = None) -> Optional[dict]:
    """Resolve a device specification from a path or short name.

    Args:
        device_arg: One of:
            - Path ending in .yaml -> load directly
            - Short name (e.g. "m1-macos") -> primitives/devices/{name}.yaml
            - None -> returns None (device spec required)

    Returns:
        Parsed device spec dict, or None if not found.
    """
    if device_arg is None:
        return None

    if device_arg.endswith(".yaml"):
        path = Path(device_arg)
    else:
        path = DEVICES_DIR / f"{device_arg}.yaml"

    if not path.exists():
        return None

    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Capability validation
# ---------------------------------------------------------------------------

def validate_capabilities(device_spec: dict) -> dict:
    """Probe runtime capabilities and degrade tier if reality doesn't match.

    Returns a deep copy with capabilities validated against actual
    runtime availability. Does not mutate the input.
    """
    validated = copy.deepcopy(device_spec)
    dev = validated.get("device", validated)

    pmu = dev.get("pmu", {})
    os_noise = dev.get("os_noise", {})

    # Probe PMU
    pmu_available = False
    if pmu.get("instruction_count", False):
        probe_result = _probe_pmu()
        pmu_available = probe_result.get("pmu_available", False)
        if not pmu_available:
            pmu["instruction_count"] = False
            pmu["backend_stall"] = False
        else:
            pmu["backend_stall"] = probe_result.get("backend_stall_available", False)

    # Probe osnoise tracer
    if os_noise.get("tracer") is not None:
        actual_tracer = _probe_osnoise()
        if actual_tracer is None:
            os_noise["tracer"] = None

    return validated


def _probe_pmu() -> dict:
    """Probe PMU availability by running cortex_inscount.

    Returns:
        {"pmu_available": bool, "cpu_freq_hz": int}
    """
    inscount_path = Path("sdk/kernel/tools/cortex_inscount")
    if not inscount_path.exists():
        return {"pmu_available": False, "cpu_freq_hz": 0}

    noop_spec_uri = Path("primitives/kernels/v1/noop@f32")
    # Verify the plugin is built (dylib/so exists)
    plugin_built = any(
        (noop_spec_uri / f"libnoop{ext}").exists()
        for ext in (".dylib", ".so")
    )
    if not plugin_built:
        return {"pmu_available": False, "cpu_freq_hz": 0}

    try:
        result = subprocess.run(
            [str(inscount_path), "--plugin", str(noop_spec_uri), "--repeats", "1"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"pmu_available": False, "cpu_freq_hz": 0}

        data = json.loads(result.stdout.strip())
        if not data.get("available", False):
            return {"pmu_available": False, "cpu_freq_hz": 0}

        return {
            "pmu_available": True,
            "cpu_freq_hz": data.get("cpu_freq_hz", 0),
            "cycle_count_available": data.get("cycle_count", 0) > 0,
            "backend_stall_available": data.get("backend_stall_cycles", 0) > 0,
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return {"pmu_available": False, "cpu_freq_hz": 0}


def _probe_osnoise() -> Optional[str]:
    """Check if osnoise tracer is available (Linux only).

    Returns:
        "osnoise" if available, None otherwise.
    """
    if platform.system() != "Linux":
        return None
    if Path("/sys/kernel/tracing/osnoise").exists():
        return "osnoise"
    return None
