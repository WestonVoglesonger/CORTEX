/* HTML Report Generator
 *
 * Generates comprehensive HTML reports with embedded SVG visualizations
 * directly from telemetry buffer after all kernels complete execution.
 */

#ifndef CORTEX_HARNESS_REPORT_H
#define CORTEX_HARNESS_REPORT_H

#include "../../telemetry/telemetry.h"

/* Generate HTML report from telemetry buffer
 *
 * Args:
 *   output_path: Full path to output HTML file
 *   telemetry: Telemetry buffer containing records from all kernels
 *   run_id: Run identifier for report header
 *
 * Returns:
 *   0 on success, -1 on failure
 */
int cortex_report_generate(const char *output_path,
                           const cortex_telemetry_buffer_t *telemetry,
                           const char *run_id);

#endif /* CORTEX_HARNESS_REPORT_H */
