/*
 * ICA (Independent Component Analysis) Kernel - ABI v3 Trainable
 *
 * Full FastICA implementation with platform-agnostic linear algebra.
 * No external dependencies (BLAS/LAPACK) - works on embedded targets.
 *
 * Workflow:
 *   1. cortex_calibrate() trains unmixing matrix W on batch data (FastICA)
 *   2. cortex_init() loads pre-trained W from calibration state
 *   3. cortex_process() applies W to each window: y = (x - mean) @ W.T
 *
 * State Format (little-endian):
 *   Bytes 0-3:   C (uint32_t) - number of channels
 *   Bytes 4-end: mean (C × float32) - channel means for centering
 *   Bytes X-end: W (C×C × float32) - unmixing matrix, row-major
 *
 * Total size: 4 + 4*C + 4*C*C bytes (16644 bytes for C=64)
 *
 * Algorithm: FastICA with symmetric decorrelation
 * - Whitening via eigendecomposition (Jacobi method)
 * - Iterative optimization with logcosh nonlinearity
 * - Symmetric decorrelation for orthogonalization
 * - Convergence tolerance: 1e-4
 * - Max iterations: 200
 */

#include "cortex_plugin.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define MAX_FASTICA_ITER 200
#define FASTICA_TOL 1e-4f
#define JACOBI_MAX_ITER 100
#define JACOBI_TOL 1e-6f

/* Runtime state (post-calibration) */
typedef struct {
    uint32_t W, C;
    float *mean;     /* Channel means [C] */
    float *W_unmix;  /* Unmixing matrix [C×C], row-major */
} ica_runtime_state_t;

/* ============================================================================
 * Embedded-Friendly Linear Algebra (NO BLAS/LAPACK dependency)
 * ============================================================================ */

/* Matrix multiply: C = A * B, all [n × n] row-major */
static void matmul_nn(const float *A, const float *B, float *C, int n) {
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            double sum = 0.0;
            for (int k = 0; k < n; k++) {
                sum += (double)A[i * n + k] * B[k * n + j];
            }
            C[i * n + j] = (float)sum;
        }
    }
}

/* Matrix multiply: C = A * B^T, A[m×n], B[p×n], C[m×p] */
static void matmul_nt(const float *A, const float *B, float *C, int m, int n, int p) {
    for (int i = 0; i < m; i++) {
        for (int j = 0; j < p; j++) {
            double sum = 0.0;
            for (int k = 0; k < n; k++) {
                sum += (double)A[i * n + k] * B[j * n + k];
            }
            C[i * p + j] = (float)sum;
        }
    }
}

/* Matrix transpose in-place [n × n] */
static void transpose_inplace(float *A, int n) {
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            float tmp = A[i * n + j];
            A[i * n + j] = A[j * n + i];
            A[j * n + i] = tmp;
        }
    }
}

/* Compute covariance matrix: C = X^T X / rows, X[rows × cols], C[cols × cols] */
static void compute_covariance(const float *X, int rows, int cols, float *C) {
    for (int i = 0; i < cols; i++) {
        for (int j = i; j < cols; j++) {  /* Symmetric, compute upper triangle */
            double sum = 0.0;
            for (int r = 0; r < rows; r++) {
                sum += (double)X[r * cols + i] * X[r * cols + j];
            }
            C[i * cols + j] = (float)(sum / rows);
            C[j * cols + i] = C[i * cols + j];  /* Mirror to lower triangle */
        }
    }
}

/* Jacobi eigendecomposition for symmetric matrix A[n×n]
 * Returns eigenvalues in D[n] and eigenvectors in V[n×n] (columns)
 * Platform-agnostic, numerically stable, no external deps */
static int jacobi_eigen(const float *A, int n, float *D, float *V) {
    /* Copy A to working matrix (will be diagonalized in-place) */
    float *B = malloc(n * n * sizeof(float));
    if (!B) return -1;
    memcpy(B, A, n * n * sizeof(float));

    /* Initialize V to identity */
    memset(V, 0, n * n * sizeof(float));
    for (int i = 0; i < n; i++) V[i * n + i] = 1.0f;

    /* Jacobi iterations */
    for (int iter = 0; iter < JACOBI_MAX_ITER; iter++) {
        /* Find largest off-diagonal element */
        float max_val = 0.0f;
        int p = 0, q = 1;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                float val = fabsf(B[i * n + j]);
                if (val > max_val) {
                    max_val = val;
                    p = i;
                    q = j;
                }
            }
        }

        /* Check convergence */
        if (max_val < JACOBI_TOL) break;

        /* Compute rotation angle */
        float b_pp = B[p * n + p];
        float b_qq = B[q * n + q];
        float b_pq = B[p * n + q];

        float theta = 0.5f * atan2f(2.0f * b_pq, b_qq - b_pp);
        float c = cosf(theta);
        float s = sinf(theta);

        /* Apply Givens rotation to B and V */
        for (int i = 0; i < n; i++) {
            float b_ip = B[i * n + p];
            float b_iq = B[i * n + q];
            B[i * n + p] = c * b_ip - s * b_iq;
            B[i * n + q] = s * b_ip + c * b_iq;

            float b_pi = B[p * n + i];
            float b_qi = B[q * n + i];
            B[p * n + i] = c * b_pi - s * b_qi;
            B[q * n + i] = s * b_pi + c * b_qi;

            float v_ip = V[i * n + p];
            float v_iq = V[i * n + q];
            V[i * n + p] = c * v_ip - s * v_iq;
            V[i * n + q] = s * v_ip + c * v_iq;
        }

        /* Update diagonal elements */
        B[p * n + p] = c * c * b_pp + s * s * b_qq - 2.0f * s * c * b_pq;
        B[q * n + q] = s * s * b_pp + c * c * b_qq + 2.0f * s * c * b_pq;
        B[p * n + q] = 0.0f;
        B[q * n + p] = 0.0f;
    }

    /* Extract diagonal (eigenvalues) */
    for (int i = 0; i < n; i++) {
        D[i] = B[i * n + i];
    }

    free(B);
    return 0;
}

/* Whiten data: Z = X * K, where K = V * D^(-1/2) * V^T
 * X[rows × cols], Z[rows × cols], eigenvectors V[cols × cols], eigenvalues D[cols] */
static int whiten_data(const float *X, int rows, int cols,
                      const float *V, const float *D, float *Z, float *K_out) {
    /* Compute whitening matrix K = V * D^(-1/2) * V^T */
    float *D_inv_sqrt = malloc(cols * cols * sizeof(float));
    float *K = malloc(cols * cols * sizeof(float));
    float *tmp = malloc(cols * cols * sizeof(float));

    if (!D_inv_sqrt || !K || !tmp) {
        free(D_inv_sqrt); free(K); free(tmp);
        return -1;
    }

    /* D_inv_sqrt = diag(1/sqrt(D)) */
    memset(D_inv_sqrt, 0, cols * cols * sizeof(float));
    for (int i = 0; i < cols; i++) {
        float eig = D[i];
        if (eig < 1e-10f) eig = 1e-10f;  /* Regularize small eigenvalues */
        D_inv_sqrt[i * cols + i] = 1.0f / sqrtf(eig);
    }

    /* K = V * D_inv_sqrt * V^T */
    matmul_nn(V, D_inv_sqrt, tmp, cols);
    matmul_nt(tmp, V, K, cols, cols, cols);

    /* Z = X * K */
    matmul_nt(X, K, Z, rows, cols, cols);

    if (K_out) memcpy(K_out, K, cols * cols * sizeof(float));

    free(D_inv_sqrt);
    free(K);
    free(tmp);
    return 0;
}

/* Nonlinearity g(u) = tanh(u), g'(u) = 1 - tanh^2(u) */
static inline float g_logcosh(float u) {
    return tanhf(u);
}

static inline float g_logcosh_deriv(float u) {
    float t = tanhf(u);
    return 1.0f - t * t;
}

/* Symmetric decorrelation: W_new = (W * W^T)^(-1/2) * W
 * Uses power iteration to approximate (W * W^T)^(-1/2) */
static void symmetric_decorrelation(float *W, int n) {
    float *WWT = malloc(n * n * sizeof(float));
    float *WWT_inv_sqrt = malloc(n * n * sizeof(float));
    float *D = malloc(n * sizeof(float));
    float *V = malloc(n * n * sizeof(float));

    if (!WWT || !WWT_inv_sqrt || !D || !V) goto cleanup;

    /* Compute WWT = W * W^T */
    matmul_nt(W, W, WWT, n, n, n);

    /* Eigendecomposition of WWT */
    if (jacobi_eigen(WWT, n, D, V) != 0) goto cleanup;

    /* Compute (WWT)^(-1/2) = V * D^(-1/2) * V^T */
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            double sum = 0.0;
            for (int k = 0; k < n; k++) {
                float d_val = D[k];
                if (d_val < 1e-10f) d_val = 1e-10f;
                sum += V[i * n + k] * (1.0 / sqrt(d_val)) * V[j * n + k];
            }
            WWT_inv_sqrt[i * n + j] = (float)sum;
        }
    }

    /* W_new = (WWT)^(-1/2) * W */
    float *W_new = malloc(n * n * sizeof(float));
    if (!W_new) goto cleanup;
    matmul_nn(WWT_inv_sqrt, W, W_new, n);
    memcpy(W, W_new, n * n * sizeof(float));
    free(W_new);

cleanup:
    free(WWT);
    free(WWT_inv_sqrt);
    free(D);
    free(V);
}

/* Full FastICA with whitening and iterative optimization */
static int fastica_full(const float *X, int rows, int cols, float *W_unmix_out) {
    fprintf(stderr, "[ica] Running full FastICA (rows=%d, cols=%d, max_iter=%d)\n",
            rows, cols, MAX_FASTICA_ITER);

    /* Allocate working memory */
    float *C = malloc(cols * cols * sizeof(float));
    float *D = malloc(cols * sizeof(float));
    float *V = malloc(cols * cols * sizeof(float));
    float *K = malloc(cols * cols * sizeof(float));
    float *Z = malloc(rows * cols * sizeof(float));
    float *W = malloc(cols * cols * sizeof(float));
    float *W_old = malloc(cols * cols * sizeof(float));
    float *gZ = malloc(rows * sizeof(float));
    float *dgZ = malloc(rows * sizeof(float));

    if (!C || !D || !V || !K || !Z || !W || !W_old || !gZ || !dgZ) {
        fprintf(stderr, "[ica] ERROR: Memory allocation failed\n");
        goto error;
    }

    /* 1. Compute covariance matrix */
    fprintf(stderr, "[ica] Computing covariance matrix...\n");
    compute_covariance(X, rows, cols, C);

    /* 2. Eigendecomposition */
    fprintf(stderr, "[ica] Running Jacobi eigendecomposition...\n");
    if (jacobi_eigen(C, cols, D, V) != 0) {
        fprintf(stderr, "[ica] ERROR: Eigendecomposition failed\n");
        goto error;
    }

    /* 3. Whiten data */
    fprintf(stderr, "[ica] Whitening data...\n");
    if (whiten_data(X, rows, cols, V, D, Z, K) != 0) {
        fprintf(stderr, "[ica] ERROR: Whitening failed\n");
        goto error;
    }

    /* 4. Initialize W randomly (orthonormal) */
    for (int i = 0; i < cols; i++) {
        for (int j = 0; j < cols; j++) {
            W[i * cols + j] = (i == j) ? 1.0f : 0.0f;
            W[i * cols + j] += sinf((float)(i * 37 + j * 17)) * 0.01f;
        }
    }
    symmetric_decorrelation(W, cols);

    /* 5. FastICA iterations */
    fprintf(stderr, "[ica] Starting FastICA iterations...\n");
    for (int iter = 0; iter < MAX_FASTICA_ITER; iter++) {
        memcpy(W_old, W, cols * cols * sizeof(float));

        /* Update each component */
        for (int comp = 0; comp < cols; comp++) {
            /* Compute w^T Z for all samples */
            for (int r = 0; r < rows; r++) {
                double sum = 0.0;
                for (int c = 0; c < cols; c++) {
                    sum += W[comp * cols + c] * Z[r * cols + c];
                }
                float u = (float)sum;
                gZ[r] = g_logcosh(u);
                dgZ[r] = g_logcosh_deriv(u);
            }

            /* w_new = E[Z g(w^T Z)] - E[g'(w^T Z)] w */
            for (int c = 0; c < cols; c++) {
                double eg = 0.0, edg = 0.0;
                for (int r = 0; r < rows; r++) {
                    eg += Z[r * cols + c] * gZ[r];
                    edg += dgZ[r];
                }
                eg /= rows;
                edg /= rows;
                W[comp * cols + c] = (float)(eg - edg * W[comp * cols + c]);
            }
        }

        /* Symmetric decorrelation */
        symmetric_decorrelation(W, cols);

        /* Check convergence: max change in any component */
        float max_change = 0.0f;
        for (int i = 0; i < cols * cols; i++) {
            float change = fabsf(W[i] - W_old[i]);
            if (change > max_change) max_change = change;
        }

        if ((iter + 1) % 10 == 0) {
            fprintf(stderr, "[ica] Iteration %d/%d: max_change=%.6f\n",
                    iter + 1, MAX_FASTICA_ITER, max_change);
        }

        if (max_change < FASTICA_TOL) {
            fprintf(stderr, "[ica] Converged at iteration %d (change=%.6f)\n",
                    iter + 1, max_change);
            break;
        }
    }

    /* 6. Compute final unmixing matrix: W_unmix = W^T * K */
    transpose_inplace(W, cols);  /* W is now W^T */
    matmul_nn(W, K, W_unmix_out, cols);

    fprintf(stderr, "[ica] FastICA complete\n");

    free(C); free(D); free(V); free(K); free(Z);
    free(W); free(W_old); free(gZ); free(dgZ);
    return 0;

error:
    free(C); free(D); free(V); free(K); free(Z);
    free(W); free(W_old); free(gZ); free(dgZ);
    return -1;
}

/* ============================================================================
 * ABI v3 Plugin Interface
 * ============================================================================ */

cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    /* Validate ABI version */
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[ica] ERROR: ABI version mismatch (expected %d, got %d)\n",
                CORTEX_ABI_VERSION, config->abi_version);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    const uint32_t W = config->window_length_samples;
    const uint32_t C = config->channels;

    fprintf(stderr, "[ica] Calibrating ICA: %u windows × %u samples × %u channels\n",
            num_windows, W, C);

    /* Concatenate windows into [num_windows*W, C] matrix */
    /* Check for overflow: num_windows * W */
    if (num_windows > 0 && W > UINT32_MAX / num_windows) {
        fprintf(stderr, "[ica] ERROR: Integer overflow in total_samples calculation\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }
    const uint32_t total_samples = num_windows * W;

    /* Check for overflow: total_samples * C * sizeof(float) */
    if (C > 0 && total_samples > SIZE_MAX / C / sizeof(float)) {
        fprintf(stderr, "[ica] ERROR: Integer overflow in allocation size\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    float *X = malloc(total_samples * C * sizeof(float));
    if (!X) {
        fprintf(stderr, "[ica] ERROR: Memory allocation failed\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Copy and reshape */
    const float *windows = (const float *)calibration_data;
    for (uint32_t win = 0; win < num_windows; win++) {
        for (uint32_t t = 0; t < W; t++) {
            for (uint32_t c = 0; c < C; c++) {
                uint32_t src_idx = win * (W * C) + t * C + c;
                uint32_t dst_idx = (win * W + t) * C + c;
                X[dst_idx] = windows[src_idx];
            }
        }
    }

    /* Compute channel means */
    float *mean = malloc(C * sizeof(float));
    if (!mean) {
        free(X);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    for (uint32_t c = 0; c < C; c++) {
        double sum = 0.0;
        for (uint32_t r = 0; r < total_samples; r++) {
            float val = X[r * C + c];
            if (!isnan(val)) sum += val;
        }
        mean[c] = (float)(sum / total_samples);
    }

    /* Center data */
    for (uint32_t r = 0; r < total_samples; r++) {
        for (uint32_t c = 0; c < C; c++) {
            uint32_t idx = r * C + c;
            X[idx] -= mean[c];
            if (isnan(X[idx])) X[idx] = 0.0f;
        }
    }

    /* Run FastICA */
    float *W_unmix = malloc(C * C * sizeof(float));
    if (!W_unmix) {
        free(X);
        free(mean);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    if (fastica_full(X, total_samples, C, W_unmix) != 0) {
        fprintf(stderr, "[ica] ERROR: FastICA failed\n");
        free(X);
        free(mean);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    free(X);

    /* Serialize state: [C (uint32) | mean (C×float32) | W (C×C×float32)] */
    /* Check for overflow: C * C */
    if (C > 0 && C > SIZE_MAX / C) {
        fprintf(stderr, "[ica] ERROR: Integer overflow in C*C calculation\n");
        free(mean);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Check for overflow: state_size calculation */
    size_t mean_size = (size_t)C * sizeof(float);
    size_t matrix_size = (size_t)C * C * sizeof(float);
    if (matrix_size > SIZE_MAX - mean_size - sizeof(uint32_t)) {
        fprintf(stderr, "[ica] ERROR: Integer overflow in state_size calculation\n");
        free(mean);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    const uint32_t state_size = sizeof(uint32_t) + mean_size + matrix_size;
    uint8_t *state_bytes = malloc(state_size);
    if (!state_bytes) {
        free(mean);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    memcpy(state_bytes, &C, sizeof(uint32_t));
    memcpy(state_bytes + sizeof(uint32_t), mean, C * sizeof(float));
    memcpy(state_bytes + sizeof(uint32_t) + C * sizeof(float), W_unmix, C * C * sizeof(float));

    free(mean);
    free(W_unmix);

    fprintf(stderr, "[ica] Calibration complete: state_size=%u bytes\n", state_size);

    return (cortex_calibration_result_t){
        .calibration_state = state_bytes,
        .state_size_bytes = state_size,
        .state_version = 1
    };
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[ica] ERROR: ABI version mismatch\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (config->calibration_state == NULL) {
        fprintf(stderr, "[ica] ERROR: Calibration state required (run 'cortex calibrate' first)\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    const uint32_t W = config->window_length_samples;

    /* Deserialize state */
    const uint8_t *bytes = (const uint8_t *)config->calibration_state;
    uint32_t C;
    memcpy(&C, bytes, sizeof(uint32_t));

    if (C != config->channels) {
        fprintf(stderr, "[ica] ERROR: Channel mismatch (state=%u, config=%u)\n",
                C, config->channels);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    ica_runtime_state_t *state = calloc(1, sizeof(ica_runtime_state_t));
    if (!state) return (cortex_init_result_t){NULL, 0, 0, 0};

    state->W = W;
    state->C = C;

    state->mean = malloc(C * sizeof(float));
    state->W_unmix = malloc(C * C * sizeof(float));

    if (!state->mean || !state->W_unmix) {
        free(state->mean);
        free(state->W_unmix);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    memcpy(state->mean, bytes + sizeof(uint32_t), C * sizeof(float));
    memcpy(state->W_unmix, bytes + sizeof(uint32_t) + C * sizeof(float), C * C * sizeof(float));

    fprintf(stderr, "[ica] Loaded calibration state: C=%u, state_size=%u bytes\n",
            C, config->calibration_state_size);

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = W,
        .output_channels = C,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}

void cortex_process(void *handle, const void *input, void *output) {
    /* Validate parameters */
    if (!handle || !input || !output) {
        fprintf(stderr, "[ica] ERROR: NULL pointer in cortex_process\n");
        return;
    }

    ica_runtime_state_t *state = (ica_runtime_state_t *)handle;
    const float *x = (const float *)input;
    float *y = (float *)output;

    const uint32_t W = state->W;
    const uint32_t C = state->C;

    /* Apply unmixing: y = (x - mean) @ W.T */
    for (uint32_t t = 0; t < W; t++) {
        for (uint32_t out_c = 0; out_c < C; out_c++) {
            double sum = 0.0;
            for (uint32_t in_c = 0; in_c < C; in_c++) {
                float x_val = x[t * C + in_c];
                if (isnan(x_val)) x_val = 0.0f;
                x_val -= state->mean[in_c];
                sum += x_val * state->W_unmix[out_c * C + in_c];
            }
            y[t * C + out_c] = (float)sum;
        }
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    ica_runtime_state_t *state = (ica_runtime_state_t *)handle;
    free(state->mean);
    free(state->W_unmix);
    free(state);
}
