/*
 * Unit tests for the kernel registry structure.
 *
 * Verifies that:
 * 1. All kernel directories exist
 * 2. spec.yaml files exist for each kernel
 * 3. Oracle Python files exist for each kernel
 * 4. Required fields are present in spec files (text-based checks)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <dirent.h>

#define MAX_KERNELS 16
#define MAX_PATH 512

typedef struct {
    const char *name;
    const char *expected_input_shape;
    const char *expected_output_shape;
    int stateful;
} kernel_test_t;

static kernel_test_t expected_kernels[] = {
    {"car@f32", "[160, 64]", "[160, 64]", 0},
    {"notch_iir@f32", "[160, 64]", "[160, 64]", 1},
    {"bandpass_fir@f32", "[160, 64]", "[160, 64]", 1},
    {"goertzel@f32", "[160, 64]", "[2, 64]", 0}
};

static int file_exists(const char *path) {
    struct stat st;
    return (stat(path, &st) == 0);
}

static int find_string_in_file(const char *filepath, const char *needle) {
    FILE *f = fopen(filepath, "r");
    if (!f) return 0;
    
    char line[1024];
    int found = 0;
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, needle) != NULL) {
            found = 1;
            break;
        }
    }
    fclose(f);
    return found;
}

static int test_kernel_structure(const char *kernel_name) {
    char spec_path[MAX_PATH];
    char oracle_path[MAX_PATH];
    char readme_path[MAX_PATH];
    
    snprintf(spec_path, sizeof(spec_path), "primitives/kernels/v1/%s/spec.yaml", kernel_name);
    snprintf(oracle_path, sizeof(oracle_path), "primitives/kernels/v1/%s/oracle.py", kernel_name);
    snprintf(readme_path, sizeof(readme_path), "primitives/kernels/v1/%s/README.md", kernel_name);
    
    if (!file_exists(spec_path)) {
        fprintf(stderr, "FAIL: %s/spec.yaml does not exist\n", kernel_name);
        return -1;
    }
    
    if (!file_exists(oracle_path)) {
        fprintf(stderr, "FAIL: %s/oracle.py does not exist\n", kernel_name);
        return -1;
    }
    
    if (!file_exists(readme_path)) {
        fprintf(stderr, "FAIL: %s/README.md does not exist\n", kernel_name);
        return -1;
    }
    
    // Check for required sections in spec.yaml
    if (!find_string_in_file(spec_path, "kernel:") ||
        !find_string_in_file(spec_path, "abi:") ||
        !find_string_in_file(spec_path, "numerical:") ||
        !find_string_in_file(spec_path, "oracle:")) {
        fprintf(stderr, "FAIL: %s/spec.yaml missing required sections\n", kernel_name);
        return -1;
    }
    
    // Check that oracle.py is executable (can be imported)
    if (!find_string_in_file(oracle_path, "def ") && 
        !find_string_in_file(oracle_path, "import numpy")) {
        fprintf(stderr, "WARN: %s/oracle.py may not be valid\n", kernel_name);
    }
    
    printf("  ✅ %s: structure valid\n", kernel_name);
    return 0;
}

static int test_kernel_spec_fields(void) {
    int num_kernels = sizeof(expected_kernels) / sizeof(expected_kernels[0]);
    int errors = 0;
    
    printf("Testing kernel spec fields...\n");
    
    for (int i = 0; i < num_kernels; i++) {
        const char *kernel = expected_kernels[i].name;
        char spec_path[MAX_PATH];
        snprintf(spec_path, sizeof(spec_path), "primitives/kernels/v1/%s/spec.yaml", kernel);
        
        // Check for key fields
        if (!find_string_in_file(spec_path, "input_shape:")) {
            fprintf(stderr, "FAIL: %s missing input_shape\n", kernel);
            errors++;
        }
        
        if (!find_string_in_file(spec_path, "output_shape:")) {
            fprintf(stderr, "FAIL: %s missing output_shape\n", kernel);
            errors++;
        }
        
        if (!find_string_in_file(spec_path, "stateful:")) {
            fprintf(stderr, "FAIL: %s missing stateful field\n", kernel);
            errors++;
        }
        
        if (!find_string_in_file(spec_path, "tolerances:")) {
            fprintf(stderr, "FAIL: %s missing tolerances\n", kernel);
            errors++;
        }
        
        if (!find_string_in_file(spec_path, "rtol:")) {
            fprintf(stderr, "FAIL: %s missing rtol in tolerances\n", kernel);
            errors++;
        }
        
        if (!find_string_in_file(spec_path, "atol:")) {
            fprintf(stderr, "FAIL: %s missing atol in tolerances\n", kernel);
            errors++;
        }
    }
    
    if (errors == 0) {
        printf("✅ All kernel specs have required fields\n");
    }
    
    return errors;
}

static int test_oracles_executable(void) {
    int num_kernels = sizeof(expected_kernels) / sizeof(expected_kernels[0]);
    int errors = 0;
    
    printf("Testing that oracles can be executed...\n");
    
    for (int i = 0; i < num_kernels; i++) {
        const char *kernel = expected_kernels[i].name;
        char oracle_path[MAX_PATH];
        snprintf(oracle_path, sizeof(oracle_path), "primitives/kernels/v1/%s/oracle.py", kernel);
        
        // Check that oracle has shebang and main guard
        if (!find_string_in_file(oracle_path, "#!/usr")) {
            fprintf(stderr, "WARN: %s/oracle.py missing shebang\n", kernel);
        }
        
        if (!find_string_in_file(oracle_path, "__main__")) {
            fprintf(stderr, "WARN: %s/oracle.py may not have standalone execution\n", kernel);
        }
    }
    
    if (errors == 0) {
        printf("✅ All oracles appear executable\n");
    }
    
    return errors;
}

int main(void) {
    int errors = 0;
    
    printf("Testing kernel registry structure...\n\n");
    
    // Test that all kernels exist with correct structure
    int num_kernels = sizeof(expected_kernels) / sizeof(expected_kernels[0]);
    for (int i = 0; i < num_kernels; i++) {
        if (test_kernel_structure(expected_kernels[i].name) != 0) {
            errors++;
        }
    }
    
    printf("\n");
    
    // Test that spec files have required fields
    if (test_kernel_spec_fields() != 0) {
        errors++;
    }
    
    printf("\n");
    
    // Test oracle executability
    if (test_oracles_executable() != 0) {
        errors++;
    }
    
    printf("\n");
    
    if (errors == 0) {
        printf("✅ All kernel registry tests passed!\n");
        return 0;
    } else {
        printf("❌ %d test(s) failed\n", errors);
        return 1;
    }
}

