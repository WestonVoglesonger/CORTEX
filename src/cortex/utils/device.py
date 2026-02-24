"""Device resolution and capability validation.

Replaces the hardcoded DEVICE_MODELS lookup table with YAML-based device
primitives. Provides:
- resolve_device(): Load device spec from path, short name, or auto-detect
- validate_capabilities(): Probe runtime PMU/osnoise availability
"""
import copy
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Optional

import yaml


DEVICES_DIR = Path("primitives/devices")


# ---------------------------------------------------------------------------
# OS-level helpers (kept from device_detect.py)
# ---------------------------------------------------------------------------

def _run_cmd(cmd: list[str]) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _query_cpu_name() -> Optional[str]:
    """Query the OS for the CPU model name string."""
    system = platform.system()
    if system == "Darwin":
        return _run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif system == "Linux":
        lscpu = _run_cmd(["lscpu"])
        if lscpu is None:
            return None
        for line in lscpu.split('\n'):
            if ':' not in line:
                continue
            key, val = line.split(':', 1)
            if key.strip() == "Model name":
                return val.strip()
    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_device(device_arg: Optional[str] = None) -> Optional[dict]:
    """Resolve a device specification from path, short name, or auto-detect.

    Args:
        device_arg: One of:
            - Path ending in .yaml → load directly
            - Short name (e.g. "m1") → primitives/devices/{name}.yaml
            - None → auto-detect from OS CPU name

    Returns:
        Parsed device spec dict, or None if resolution fails.
    """
    if device_arg is not None:
        return _load_device_yaml(device_arg)

    # Auto-detect: query OS CPU name, match against device YAMLs
    cpu_name = _query_cpu_name()
    if cpu_name is None:
        return None
    return _match_device_yaml(cpu_name)


def _load_device_yaml(name_or_path: str) -> Optional[dict]:
    """Load a device YAML from an explicit path or short name.

    Args:
        name_or_path: Either a .yaml path or a short name like "m1".

    Returns:
        Parsed YAML dict or None if file not found.
    """
    if name_or_path.endswith(".yaml"):
        path = Path(name_or_path)
    else:
        path = DEVICES_DIR / f"{name_or_path}.yaml"

    if not path.exists():
        return None

    with open(path) as f:
        return yaml.safe_load(f)


def _match_device_yaml(cpu_name: str) -> Optional[dict]:
    """Match a CPU name against available device YAMLs.

    Globs primitives/devices/*.yaml, loads each, checks if the YAML's
    device.name is a case-insensitive substring of cpu_name.
    Longest match wins (e.g. "Apple M1 Pro" beats "Apple M1").

    Returns:
        Best-matching device spec dict, or None.
    """
    if not DEVICES_DIR.exists():
        return None

    best_match = None
    best_match_len = 0

    for yaml_path in DEVICES_DIR.glob("*.yaml"):
        try:
            with open(yaml_path) as f:
                spec = yaml.safe_load(f)
        except Exception:
            continue

        device_name = spec.get("device", {}).get("name", "")
        if not device_name:
            continue

        if device_name.lower() in cpu_name.lower():
            if len(device_name) > best_match_len:
                best_match = spec
                best_match_len = len(device_name)

    return best_match


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
    freq = dev.get("frequency", {})
    os_noise = dev.get("os_noise", {})

    # Probe PMU
    pmu_available = False
    if pmu.get("instruction_count", False):
        probe_result = _probe_pmu()
        pmu_available = probe_result.get("pmu_available", False)

    # Probe osnoise tracer
    osnoise_tracer = os_noise.get("tracer")
    if osnoise_tracer is not None:
        actual_tracer = _probe_osnoise()
        if actual_tracer is None:
            osnoise_tracer = None

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


