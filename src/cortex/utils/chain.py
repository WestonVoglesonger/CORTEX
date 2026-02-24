"""Chain validation and configuration for SE-8 chained pipeline execution."""
import yaml
from pathlib import Path
from typing import List, Optional, Tuple


def _shape_dim(shape, index):
    """Extract a dimension from a shape list, or None if absent/dynamic."""
    if isinstance(shape, list) and len(shape) > index:
        return shape[index]
    return None


def validate_chain(kernel_names: List[str], kernels_dir: str = "primitives/kernels") -> Tuple[bool, Optional[str]]:
    """Validate dimension compatibility for a chain of kernels.

    For a valid chain: kernel[i].output_shape must be compatible with kernel[i+1].input_shape.
    Shape-preserving kernels (where output_shape matches input_shape) are always compatible.

    Args:
        kernel_names: Ordered list of kernel names to chain
        kernels_dir: Base directory for kernel primitives

    Returns:
        (valid, error_message) tuple. If valid=True, error_message is None.
    """
    if len(kernel_names) < 2:
        return False, "Chain requires at least 2 kernels"

    specs = []
    kernels_path = Path(kernels_dir)

    for name in kernel_names:
        spec = _load_kernel_spec(name, kernels_path)
        if spec is None:
            return False, f"Kernel spec not found: {name}"
        specs.append((name, spec))

    # Check dimension compatibility between consecutive kernels
    for i in range(len(specs) - 1):
        name_a, spec_a = specs[i]
        name_b, spec_b = specs[i + 1]

        output_shape = spec_a.get('abi', {}).get('output_shape')
        input_shape = spec_b.get('abi', {}).get('input_shape')

        if output_shape is None or input_shape is None:
            continue

        # Compare W dimension. None (from null in YAML) means dynamic — always compatible.
        out_w = _shape_dim(output_shape, 0)
        in_w = _shape_dim(input_shape, 0)
        if out_w is not None and in_w is not None and out_w != in_w:
            return False, (f"Dimension mismatch: {name_a} output W={out_w} "
                           f"!= {name_b} input W={in_w}")

        # Compare C dimension
        out_c = _shape_dim(output_shape, 1)
        in_c = _shape_dim(input_shape, 1)
        if out_c is not None and in_c is not None and out_c != in_c:
            return False, (f"Channel mismatch: {name_a} output C={out_c} "
                           f"!= {name_b} input C={in_c}")

    return True, None


def _load_kernel_spec(kernel_name: str, kernels_path: Path) -> Optional[dict]:
    """Load a kernel's spec.yaml file."""
    # Search versioned directories
    for version_dir in sorted(kernels_path.glob("v*")):
        for kernel_dir in version_dir.glob(f"{kernel_name}@*"):
            spec_file = kernel_dir / "spec.yaml"
            if spec_file.exists():
                with open(spec_file) as f:
                    return yaml.safe_load(f)
    return None
