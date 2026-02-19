"""Instruction-level analysis of compiled kernel binaries.

Disassembles compiled kernel .dylib/.so files using otool (macOS) or objdump (Linux)
and counts instruction types in cortex_process() for Roofline prediction.

Also provides hardware PMU-based dynamic instruction counting via cortex_inscount.
"""
import json
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cortex.utils.discovery import find_kernel


@dataclass
class InstructionProfile:
    """Instruction counts from disassembly of cortex_process()."""
    kernel_name: str
    total_instructions: int
    arithmetic_count: int       # FP arithmetic ops
    load_count: int             # Memory loads
    store_count: int            # Memory stores
    branch_count: int           # Control flow
    simd_count: int             # Vector instructions (subset of arithmetic)
    simd_width: int             # Elements per SIMD op (4 for NEON f32, 8 for AVX f32)
    estimated_flops: int        # arithmetic_count * simd_width (for SIMD ops)
    arch: str                   # "aarch64" or "x86_64"


# ARM64 (aarch64) instruction classification
ARM64_ARITHMETIC = {
    'fadd', 'fsub', 'fmul', 'fdiv', 'fmadd', 'fmsub', 'fnmadd', 'fnmsub',
    'fmla', 'fmls', 'fneg', 'fabs', 'fsqrt', 'frint',
    'add', 'sub', 'mul', 'madd', 'msub',
    'scvtf', 'ucvtf', 'fcvtzs', 'fcvtzu',
}

ARM64_LOAD = {
    'ldr', 'ldp', 'ldur', 'ldrb', 'ldrh', 'ldrsw', 'ldrsh', 'ldrsb',
    'ld1', 'ld2', 'ld3', 'ld4', 'ldar', 'ldaxr', 'ldxr',
}

ARM64_STORE = {
    'str', 'stp', 'stur', 'strb', 'strh',
    'st1', 'st2', 'st3', 'st4', 'stlr', 'stxr', 'stlxr',
}

ARM64_BRANCH = {
    'b', 'bl', 'br', 'blr', 'ret',
    'cbz', 'cbnz', 'tbz', 'tbnz',
    'b.eq', 'b.ne', 'b.lt', 'b.le', 'b.gt', 'b.ge',
    'b.hi', 'b.hs', 'b.lo', 'b.ls', 'b.mi', 'b.pl',
    'b.vs', 'b.vc', 'b.al',
}

# SIMD indicators for ARM64: instructions operating on v-registers
ARM64_SIMD_MNEMONICS = {
    'fmla', 'fmls', 'fadd', 'fsub', 'fmul', 'fdiv',
    'ld1', 'ld2', 'st1', 'st2',
}

# x86_64 instruction classification
X86_ARITHMETIC = {
    'addss', 'addsd', 'addps', 'addpd',
    'subss', 'subsd', 'subps', 'subpd',
    'mulss', 'mulsd', 'mulps', 'mulpd',
    'divss', 'divsd', 'divps', 'divpd',
    'sqrtss', 'sqrtsd', 'sqrtps', 'sqrtpd',
    'vaddss', 'vaddsd', 'vaddps', 'vaddpd',
    'vsubss', 'vsubsd', 'vsubps', 'vsubpd',
    'vmulss', 'vmulsd', 'vmulps', 'vmulpd',
    'vdivss', 'vdivsd', 'vdivps', 'vdivpd',
    'vfmadd132ss', 'vfmadd213ss', 'vfmadd231ss',
    'vfmadd132sd', 'vfmadd213sd', 'vfmadd231sd',
    'vfmadd132ps', 'vfmadd213ps', 'vfmadd231ps',
    'vfmadd132pd', 'vfmadd213pd', 'vfmadd231pd',
}

X86_LOAD = {
    'movss', 'movsd', 'movaps', 'movups', 'movapd', 'movupd',
    'vmovss', 'vmovsd', 'vmovaps', 'vmovups', 'vmovapd', 'vmovupd',
    'mov', 'movzx', 'movsx',
}

X86_STORE = set()  # x86 uses same mnemonics for load/store; disambiguated by operand direction

X86_BRANCH = {
    'jmp', 'je', 'jne', 'jl', 'jle', 'jg', 'jge',
    'ja', 'jae', 'jb', 'jbe', 'jz', 'jnz',
    'call', 'ret',
}

X86_SIMD_PREFIXES = {'v', 'addp', 'subp', 'mulp', 'divp'}


def _get_library_path(kernel_name: str) -> Optional[Path]:
    """Find the compiled library for a kernel."""
    kernel_info = find_kernel(kernel_name)
    if kernel_info is None:
        return None

    spec_uri = Path(kernel_info['spec_uri'])
    lib_name = f"lib{kernel_info['name']}"

    dylib = spec_uri / f"{lib_name}.dylib"
    if dylib.exists():
        return dylib

    so = spec_uri / f"{lib_name}.so"
    if so.exists():
        return so

    return None


def _disassemble(library_path: Path) -> Optional[str]:
    """Disassemble a library using otool (macOS) or objdump (Linux)."""
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["otool", "-tv", str(library_path)],
                capture_output=True, text=True, timeout=30
            )
        else:
            result = subprocess.run(
                ["objdump", "-d", str(library_path)],
                capture_output=True, text=True, timeout=30
            )
        if result.returncode != 0:
            return None
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _extract_function_instructions(disasm: str, func_name: str = "cortex_process") -> list[str]:
    """Extract instruction lines for a specific function from disassembly output.

    Searches for both _cortex_process (macOS name-mangled) and cortex_process.
    """
    lines = disasm.split('\n')
    in_function = False
    instructions = []

    # Patterns to detect function boundaries
    # macOS otool: "_cortex_process:" at start of line
    # Linux objdump: "<cortex_process>:" in line
    func_patterns = [f"_{func_name}:", f"<{func_name}>:", f"{func_name}:"]

    for line in lines:
        stripped = line.strip()

        if not in_function:
            for pattern in func_patterns:
                if pattern in stripped:
                    in_function = True
                    break
            continue

        # End of function: next symbol boundary (new label)
        # macOS otool: line starts with symbol name (no leading whitespace, ends with ':')
        # Linux objdump: line with <symbol_name>:
        if in_function and stripped and not stripped.startswith('0'):
            # Check if this is a new symbol (not a branch label within the function)
            if ':' in stripped and not stripped.startswith(';'):
                # macOS: new function symbols don't start with hex
                if re.match(r'^[_a-zA-Z]', stripped):
                    break

        # Parse instruction line
        # macOS otool format: "0x00000abc\t<hex>\t<mnemonic>\t<operands>"
        # Linux objdump format: "   abc:\t<hex>\t<mnemonic>\t<operands>"
        if '\t' in stripped or '  ' in stripped:
            # Extract mnemonic (skip address and hex bytes)
            parts = re.split(r'\t+|\s{2,}', stripped)
            for part in parts:
                part = part.strip()
                # Skip hex addresses and byte sequences
                if not part or re.match(r'^(0x)?[0-9a-fA-F]+:?$', part):
                    continue
                if re.match(r'^([0-9a-fA-F]{2}\s)+', part):
                    continue
                # This should be the mnemonic + operands
                instructions.append(part)
                break

    return instructions


def _classify_arm64(instructions: list[str]) -> InstructionProfile:
    """Classify ARM64 instructions."""
    arithmetic = load = store = branch = simd = 0

    for instr in instructions:
        parts = instr.split()
        if not parts:
            continue
        mnemonic = parts[0].lower().rstrip(',')
        operands = ' '.join(parts[1:]) if len(parts) > 1 else ''

        # Check for SIMD: v-register operands
        is_simd = bool(re.search(r'\bv\d+', operands))

        if mnemonic in ARM64_ARITHMETIC or mnemonic.rstrip('0123456789') in ARM64_ARITHMETIC:
            arithmetic += 1
            if is_simd or mnemonic in ARM64_SIMD_MNEMONICS:
                simd += 1
        elif mnemonic in ARM64_LOAD or mnemonic.split('.')[0] in ARM64_LOAD:
            load += 1
        elif mnemonic in ARM64_STORE or mnemonic.split('.')[0] in ARM64_STORE:
            store += 1
        elif mnemonic in ARM64_BRANCH or mnemonic.split('.')[0] in ARM64_BRANCH:
            branch += 1

    simd_width = 4  # NEON f32: 128-bit / 32-bit = 4
    estimated_flops = simd * simd_width + (arithmetic - simd)
    total = arithmetic + load + store + branch

    return InstructionProfile(
        kernel_name="",  # filled by caller
        total_instructions=len(instructions),
        arithmetic_count=arithmetic,
        load_count=load,
        store_count=store,
        branch_count=branch,
        simd_count=simd,
        simd_width=simd_width,
        estimated_flops=max(estimated_flops, 0),
        arch="aarch64",
    )


def _classify_x86_64(instructions: list[str]) -> InstructionProfile:
    """Classify x86_64 instructions."""
    arithmetic = load = store = branch = simd = 0

    for instr in instructions:
        parts = instr.split()
        if not parts:
            continue
        mnemonic = parts[0].lower()
        operands = ' '.join(parts[1:]) if len(parts) > 1 else ''

        # x86: disambiguate load vs store by operand order (AT&T: src, dst)
        has_memory = bool(re.search(r'\(', operands))

        if mnemonic in X86_ARITHMETIC:
            arithmetic += 1
            # Packed (ps/pd) or v-prefixed = SIMD
            if mnemonic.endswith(('ps', 'pd')) or mnemonic.startswith('v'):
                simd += 1
        elif mnemonic in X86_LOAD and has_memory:
            load += 1
        elif mnemonic in X86_BRANCH:
            branch += 1
        elif mnemonic in X86_LOAD and not has_memory:
            # Register-to-register move, not a memory access
            pass
        elif has_memory and mnemonic.startswith(('mov', 'vmov')):
            # Heuristic: if memory operand is destination, it's a store
            # AT&T syntax: last operand is destination
            op_parts = operands.split(',')
            if len(op_parts) >= 2 and '(' in op_parts[-1]:
                store += 1
            else:
                load += 1

    # AVX f32: 256-bit / 32-bit = 8; SSE: 128-bit / 32-bit = 4
    simd_width = 8 if any('ymm' in i.lower() for i in instructions) else 4
    estimated_flops = simd * simd_width + (arithmetic - simd)
    total = arithmetic + load + store + branch

    return InstructionProfile(
        kernel_name="",
        total_instructions=len(instructions),
        arithmetic_count=arithmetic,
        load_count=load,
        store_count=store,
        branch_count=branch,
        simd_count=simd,
        simd_width=simd_width,
        estimated_flops=max(estimated_flops, 0),
        arch="x86_64",
    )


def count_dynamic_instructions(
    kernel_name: str,
    window_length: int = 160,
    channels: int = 64,
) -> Optional[dict]:
    """Count retired instructions for a single cortex_process() call via hardware PMU.

    Runs the cortex_inscount tool as a subprocess. Returns the median instruction
    count and CPU frequency, or None if PMU is unavailable or the tool isn't built.

    Args:
        kernel_name: Kernel name (e.g., 'bandpass_fir')
        window_length: Samples per window
        channels: Number of channels

    Returns:
        Dict with {"instruction_count": int, "cpu_freq_hz": int} or None.
    """
    # Find the cortex_inscount binary relative to project root
    tool_path = Path(__file__).resolve().parents[3] / "sdk" / "kernel" / "tools" / "cortex_inscount"
    if not tool_path.exists():
        return None

    kernel_info = find_kernel(kernel_name)
    if kernel_info is None:
        return None

    spec_uri = kernel_info['spec_uri']

    try:
        result = subprocess.run(
            [
                str(tool_path),
                "--plugin", spec_uri,
                "--channels", str(channels),
                "--window-length", str(window_length),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return None

    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None

    if not data.get("available", False):
        return None

    count = data.get("instruction_count", 0)
    if count <= 0:
        return None

    return {
        "instruction_count": count,
        "cpu_freq_hz": data.get("cpu_freq_hz", 0),
    }


def analyze_kernel(kernel_name: str) -> Optional[InstructionProfile]:
    """Analyze a compiled kernel's cortex_process() function.

    Args:
        kernel_name: Name of the kernel (e.g., 'bandpass_fir')

    Returns:
        InstructionProfile or None if kernel not built or disassembly fails.
    """
    lib_path = _get_library_path(kernel_name)
    if lib_path is None:
        return None

    disasm = _disassemble(lib_path)
    if disasm is None:
        return None

    instructions = _extract_function_instructions(disasm)
    if not instructions:
        return None

    arch = platform.machine()
    if arch in ("arm64", "aarch64"):
        profile = _classify_arm64(instructions)
    elif arch in ("x86_64", "AMD64"):
        profile = _classify_x86_64(instructions)
    else:
        return None

    profile.kernel_name = kernel_name
    return profile
