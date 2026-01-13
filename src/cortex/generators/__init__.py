"""
CORTEX synthetic dataset generator integration.

Provides:
- is_generator_dataset(): Detect generator-based datasets
- execute_generator(): Run generator and get output file
- process_config_with_generators(): High-level CLI integration
- save_generation_manifest(): Save manifest to results
- cleanup_temp_files(): Clean up temporary files
"""

from .integration import (
    is_generator_dataset,
    execute_generator,
    process_config_with_generators,
    save_generation_manifest,
    cleanup_temp_files
)

__all__ = [
    'is_generator_dataset',
    'execute_generator',
    'process_config_with_generators',
    'save_generation_manifest',
    'cleanup_temp_files'
]
