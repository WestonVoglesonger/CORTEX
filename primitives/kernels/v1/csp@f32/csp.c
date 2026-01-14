/*
 * CSP (Common Spatial Pattern) Kernel - ABI v3 Trainable
 *
 * Spatial filtering for motor imagery classification.
 * Finds filters that maximize variance ratio between two classes.
 *
 * Workflow:
 *   1. cortex_calibrate() trains spatial filters W on labeled trials
 *   2. cortex_init() loads pre-trained W from calibration state
 *   3. cortex_process() applies W to each window: y = x @ W
 *
 * State Format (little-endian):
 *   Bytes 0-3:   n_channels (uint32_t)
 *   Bytes 4-7:   n_components (uint32_t)
 *   Bytes 8-end: W (n_components × n_channels × float32) - spatial filters, column-major
 *
 * Total size: 8 + 4*n_channels*n_components bytes (1032 bytes for 64ch, 4 components)
 *
 * Algorithm: CSP via whitening (Ramoser et al. 2000)
 * - Compute per-class covariance matrices C0, C1
 * - Whiten using composite covariance C = C0 + C1
 * - Eigendecompose whitened class covariance
 * - Extract top-m and bottom-m eigenvectors as spatial filters
 */

#include "cortex_plugin.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define CORTEX_ABI_VERSION 3u

/* Improved Jacobi parameters (cyclic sweeps, not iterations) */
#define JACOBI_MAX_SWEEPS 50      /* Maximum full sweeps through all (p,q) pairs */
#define JACOBI_TOL 1e-6           /* Convergence tolerance for Frobenius norm */
#define JACOBI_ORTHO_FREQ 10      /* Apply Gram-Schmidt every N sweeps */

/* Runtime state (post-calibration) */
typedef struct {
    uint32_t W, C;
    uint32_t n_components;
    float *W_filters;  /* CSP spatial filters [n_components × C], column-major */
} csp_runtime_state_t;

/* ============================================================================
 * Linear Algebra Helpers (Reused from ICA pattern)
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

/* ============================================================================
 * Improved Jacobi Eigendecomposition
 *
 * Implementation based on:
 * - Cyclic Jacobi method (Golub & Van Loan Algorithm 8.4.3)
 * - GSL's symschur2 for numerically stable Givens rotations
 * - Double precision intermediate calculations
 * - Gram-Schmidt orthogonalization for eigenvector correction
 * ============================================================================ */

/* Helper 1: Compute Frobenius norm of off-diagonal elements */
static double off_diagonal_norm(const float *B, int n) {
    double norm = 0.0;
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            double val = B[i * n + j];
            norm += val * val;
        }
    }
    return sqrt(norm);
}

/* Helper 2: GSL-style Givens rotation parameters (double precision for stability)
 *
 * Computes c, s such that the Givens rotation J = [[c, -s], [s, c]]
 * zeros the off-diagonal element a_pq in a symmetric 2×2 submatrix.
 *
 * Uses overflow-safe formulation:
 *   tau = (a_qq - a_pp) / (2 * a_pq)
 *   t = sign(tau) / (|tau| + sqrt(1 + tau²))
 *   c = 1 / sqrt(1 + t²)
 *   s = t * c
 */
static void symschur2(double a_pp, double a_qq, double a_pq,
                      double *c_out, double *s_out) {
    if (fabs(a_pq) < 1e-15) {
        /* Already diagonal, no rotation needed */
        *c_out = 1.0;
        *s_out = 0.0;
        return;
    }

    double tau = (a_qq - a_pp) / (2.0 * a_pq);
    double t;

    if (tau >= 0.0) {
        t = 1.0 / (tau + hypot(1.0, tau));  /* Overflow-safe */
    } else {
        t = -1.0 / (-tau + hypot(1.0, tau));
    }

    double c = 1.0 / sqrt(1.0 + t * t);
    double s = t * c;

    *c_out = c;
    *s_out = s;
}

/* Helper 3: Modified Gram-Schmidt orthogonalization for eigenvector matrix V
 *
 * Corrects accumulated rounding errors by re-orthogonalizing columns of V.
 * Essential for maintaining eigenvector orthogonality in float32.
 */
static void gram_schmidt(float *V, int n) {
    for (int j = 0; j < n; j++) {
        /* Orthogonalize column j against all previous columns */
        for (int k = 0; k < j; k++) {
            double dot = 0.0;
            for (int i = 0; i < n; i++) {
                dot += (double)V[i * n + j] * (double)V[i * n + k];
            }
            for (int i = 0; i < n; i++) {
                V[i * n + j] -= (float)(dot * V[i * n + k]);
            }
        }

        /* Normalize column j */
        double norm = 0.0;
        for (int i = 0; i < n; i++) {
            double val = V[i * n + j];
            norm += val * val;
        }
        norm = sqrt(norm);

        if (norm > 1e-15) {
            for (int i = 0; i < n; i++) {
                V[i * n + j] /= (float)norm;
            }
        }
    }
}

/* Improved Cyclic Jacobi eigendecomposition for symmetric matrix A[n×n]
 * Returns eigenvalues in D[n] (descending order) and eigenvectors in V[n×n] (columns) */
static int jacobi_eigen(const float *A, int n, float *D, float *V) {
    /* Check overflow */
    if (n > 0 && (size_t)n > SIZE_MAX / n / sizeof(float)) {
        fprintf(stderr, "[jacobi] ERROR: Overflow in jacobi_eigen (n=%d)\n", n);
        return -1;
    }

    /* Copy A to working matrix */
    float *B = malloc((size_t)n * n * sizeof(float));
    if (!B) return -1;
    memcpy(B, A, n * n * sizeof(float));

    /* Initialize V to identity */
    memset(V, 0, n * n * sizeof(float));
    for (int i = 0; i < n; i++) V[i * n + i] = 1.0f;

    fprintf(stderr, "[jacobi] Starting cyclic Jacobi: n=%d, max_sweeps=%d\n", n, JACOBI_MAX_SWEEPS);

    int final_sweep = 0;
    for (int sweep = 0; sweep < JACOBI_MAX_SWEEPS; sweep++) {
        /* Cyclic Jacobi: Process all (p,q) pairs in predetermined order */
        for (int p = 0; p < n - 1; p++) {
            for (int q = p + 1; q < n; q++) {
                /* Compute Givens rotation using symschur2 (double precision) */
                double c, s;
                symschur2((double)B[p * n + p], (double)B[q * n + q],
                         (double)B[p * n + q], &c, &s);

                /* Convert to float for matrix updates */
                float cf = (float)c;
                float sf = (float)s;

                /* Apply rotation to B: B' = J^T * B * J */
                /* Update rows p and q of B */
                for (int i = 0; i < n; i++) {
                    float b_ip = B[i * n + p];
                    float b_iq = B[i * n + q];
                    B[i * n + p] = cf * b_ip - sf * b_iq;
                    B[i * n + q] = sf * b_ip + cf * b_iq;
                }

                /* Update columns p and q of B */
                for (int i = 0; i < n; i++) {
                    float b_pi = B[p * n + i];
                    float b_qi = B[q * n + i];
                    B[p * n + i] = cf * b_pi - sf * b_qi;
                    B[q * n + i] = sf * b_pi + cf * b_qi;
                }

                /* Accumulate eigenvectors: V' = V * J */
                for (int i = 0; i < n; i++) {
                    float v_ip = V[i * n + p];
                    float v_iq = V[i * n + q];
                    V[i * n + p] = cf * v_ip - sf * v_iq;
                    V[i * n + q] = sf * v_ip + cf * v_iq;
                }
            }
        }

        /* Check convergence: Frobenius norm of off-diagonals */
        double off_norm = off_diagonal_norm(B, n);
        if (off_norm < JACOBI_TOL) {
            final_sweep = sweep;
            fprintf(stderr, "[jacobi] Converged at sweep %d (off_norm=%.2e)\n", sweep, off_norm);
            break;
        }
        final_sweep = sweep;

        /* Apply Gram-Schmidt orthogonalization periodically */
        if ((sweep + 1) % JACOBI_ORTHO_FREQ == 0) {
            gram_schmidt(V, n);
        }
    }

    /* Final Gram-Schmidt pass to ensure orthogonality */
    gram_schmidt(V, n);

    /* Extract eigenvalues from diagonal */
    for (int i = 0; i < n; i++) {
        D[i] = B[i * n + i];
    }

    /* Check for numerical errors */
    int nan_count = 0;
    for (int i = 0; i < n; i++) {
        if (isnan(D[i]) || isinf(D[i])) nan_count++;
    }
    if (nan_count > 0) {
        fprintf(stderr, "[jacobi] ERROR: %d/%d eigenvalues are NaN/Inf after %d sweeps\n",
                nan_count, n, final_sweep);
        free(B);
        return -1;
    }

    /* Sort eigenvalues descending and reorder eigenvectors */
    for (int i = 0; i < n - 1; i++) {
        int max_idx = i;
        for (int j = i + 1; j < n; j++) {
            if (D[j] > D[max_idx]) max_idx = j;
        }
        if (max_idx != i) {
            /* Swap eigenvalues */
            float tmp = D[i];
            D[i] = D[max_idx];
            D[max_idx] = tmp;

            /* Swap eigenvector columns */
            for (int k = 0; k < n; k++) {
                float tmp_v = V[k * n + i];
                V[k * n + i] = V[k * n + max_idx];
                V[k * n + max_idx] = tmp_v;
            }
        }
    }

    fprintf(stderr, "[jacobi] Eigenvalue range: [%.6f, %.6f] (converged in %d sweeps)\n",
            D[n-1], D[0], final_sweep);

    free(B);
    return 0;
}

/* ============================================================================
 * CSP Calibration Algorithm (Trainable - ABI v3)
 * ============================================================================ */

cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *training_data,
    uint32_t num_windows
) {
    fprintf(stderr, "[csp] Starting calibration with %u windows\n", num_windows);

    const uint32_t C = config->channels;
    const uint32_t W = config->window_length_samples;
    const float *data = (const float *)training_data;

    /* Parse parameters: n_components and labels */
    uint32_t n_components = 4;
    uint32_t *labels = NULL;

    if (config->kernel_params) {
        const char *params = (const char *)config->kernel_params;

        /* Parse n_components */
        const char *comp_str = strstr(params, "n_components=");
        if (comp_str) sscanf(comp_str, "n_components=%u", &n_components);

        /* Parse labels (comma-separated) */
        const char *labels_str = strstr(params, "labels=");
        if (labels_str) {
            labels = malloc(num_windows * sizeof(uint32_t));
            if (!labels) return (cortex_calibration_result_t){NULL, 0, 0};

            labels_str += strlen("labels=");
            for (uint32_t i = 0; i < num_windows; i++) {
                if (sscanf(labels_str, "%u", &labels[i]) != 1) {
                    free(labels);
                    return (cortex_calibration_result_t){NULL, 0, 0};
                }
                labels_str = strchr(labels_str, ',');
                if (!labels_str && i < num_windows - 1) {
                    free(labels);
                    return (cortex_calibration_result_t){NULL, 0, 0};
                }
                if (labels_str) labels_str++;
            }
        } else {
            fprintf(stderr, "[csp] ERROR: No labels in kernel_params\n");
            return (cortex_calibration_result_t){NULL, 0, 0};
        }
    } else {
        fprintf(stderr, "[csp] ERROR: kernel_params is NULL\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Allocate covariance matrices */
    float *C0 = calloc(C * C, sizeof(float));
    float *C1 = calloc(C * C, sizeof(float));
    if (!C0 || !C1) {
        free(C0); free(C1); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Count classes */
    uint32_t count0 = 0, count1 = 0;
    for (uint32_t i = 0; i < num_windows; i++) {
        if (labels[i] == 0) count0++;
        else count1++;
    }

    fprintf(stderr, "[csp] Classes: class0=%u, class1=%u\n", count0, count1);

    /* Compute per-class average covariances */
    for (uint32_t trial = 0; trial < num_windows; trial++) {
        const float *X = data + trial * W * C;

        /* Trial covariance */
        for (uint32_t i = 0; i < C; i++) {
            for (uint32_t j = i; j < C; j++) {
                double sum = 0.0;
                for (uint32_t t = 0; t < W; t++) {
                    sum += (double)X[t * C + i] * X[t * C + j];
                }
                float cov = (float)(sum / W);

                if (labels[trial] == 0) {
                    C0[i * C + j] += cov / count0;
                    C0[j * C + i] = C0[i * C + j];
                } else {
                    C1[i * C + j] += cov / count1;
                    C1[j * C + i] = C1[i * C + j];
                }
            }
        }
    }

    /* Add regularization for numerical stability (match Python oracle) */
    const float reg = 1e-6f;
    for (uint32_t i = 0; i < C; i++) {
        C0[i * C + i] += reg;
        C1[i * C + i] += reg;
    }

    /* Debug: Check C0 and C1 diagonal values */
    float c0_min_diag = C0[0], c0_max_diag = C0[0];
    float c1_min_diag = C1[0], c1_max_diag = C1[0];
    for (uint32_t i = 0; i < C; i++) {
        if (C0[i * C + i] < c0_min_diag) c0_min_diag = C0[i * C + i];
        if (C0[i * C + i] > c0_max_diag) c0_max_diag = C0[i * C + i];
        if (C1[i * C + i] < c1_min_diag) c1_min_diag = C1[i * C + i];
        if (C1[i * C + i] > c1_max_diag) c1_max_diag = C1[i * C + i];
    }
    fprintf(stderr, "[csp] C0 diagonal range: [%.6f, %.6f]\n", c0_min_diag, c0_max_diag);
    fprintf(stderr, "[csp] C1 diagonal range: [%.6f, %.6f]\n", c1_min_diag, c1_max_diag);

    /* Composite covariance C = C0 + C1 */
    float *C_comp = malloc(C * C * sizeof(float));
    if (!C_comp) {
        free(C0); free(C1); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }
    for (uint32_t i = 0; i < C * C; i++) C_comp[i] = C0[i] + C1[i];

    /* Debug: Verify symmetry of composite matrix */
    float max_asymm = 0.0f;
    for (uint32_t i = 0; i < C; i++) {
        for (uint32_t j = i + 1; j < C; j++) {
            float diff = fabsf(C_comp[i * C + j] - C_comp[j * C + i]);
            if (diff > max_asymm) max_asymm = diff;
        }
    }
    fprintf(stderr, "[csp] Composite matrix max asymmetry: %.2e\n", max_asymm);

    /* Eigendecompose C = U Λ U^T using LAPACK */
    float *lambda = malloc(C * sizeof(float));
    float *U = malloc(C * C * sizeof(float));
    if (!lambda || !U || jacobi_eigen(C_comp, C, lambda, U) != 0) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Whitening matrix P = Λ^(-1/2) U^T */
    float *P = malloc(C * C * sizeof(float));
    if (!P) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }
    for (uint32_t i = 0; i < C; i++) {
        float scale = 1.0f / sqrtf(lambda[i] + 1e-8f);
        for (uint32_t j = 0; j < C; j++) {
            P[i * C + j] = scale * U[j * C + i];  /* U^T with scaling */
        }
    }

    /* Whitened C1: S1 = P C1 P^T */
    float *PC1 = malloc(C * C * sizeof(float));
    float *S1 = malloc(C * C * sizeof(float));
    if (!PC1 || !S1) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P); free(PC1); free(S1); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    matmul_nn(P, C1, PC1, C);
    for (uint32_t i = 0; i < C; i++) {
        for (uint32_t j = 0; j < C; j++) {
            double sum = 0.0;
            for (uint32_t k = 0; k < C; k++) {
                sum += (double)PC1[i * C + k] * P[j * C + k];
            }
            S1[i * C + j] = (float)sum;
        }
    }

    /* Eigendecompose S1 = B D B^T using LAPACK */
    float *D = malloc(C * sizeof(float));
    float *B = malloc(C * C * sizeof(float));
    if (!D || !B || jacobi_eigen(S1, C, D, B) != 0) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P); free(PC1); free(S1); free(D); free(B); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* CSP filters W = B^T P */
    float *W_full = malloc(C * C * sizeof(float));
    if (!W_full) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P); free(PC1); free(S1); free(D); free(B); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }
    for (uint32_t i = 0; i < C; i++) {
        for (uint32_t j = 0; j < C; j++) {
            double sum = 0.0;
            for (uint32_t k = 0; k < C; k++) {
                sum += (double)B[k * C + i] * P[k * C + j];
            }
            W_full[i * C + j] = (float)sum;
        }
    }

    /* Select top-m and bottom-m filters */
    uint32_t m = n_components / 2;
    float *W_sel = malloc(C * n_components * sizeof(float));
    if (!W_sel) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P); free(PC1); free(S1); free(D); free(B); free(W_full); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    for (uint32_t i = 0; i < m; i++) {
        memcpy(W_sel + i * C, W_full + i * C, C * sizeof(float));
        memcpy(W_sel + (m + i) * C, W_full + (C - m + i) * C, C * sizeof(float));
    }

    /* Serialize state */
    size_t state_size = 2 * sizeof(uint32_t) + C * n_components * sizeof(float);
    void *state = malloc(state_size);
    if (!state) {
        free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P); free(PC1); free(S1); free(D); free(B); free(W_full); free(W_sel); free(labels);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    uint8_t *ptr = (uint8_t *)state;
    memcpy(ptr, &C, 4); ptr += 4;
    memcpy(ptr, &n_components, 4); ptr += 4;

    /* Store as column-major */
    for (uint32_t i = 0; i < C; i++) {
        for (uint32_t j = 0; j < n_components; j++) {
            memcpy(ptr, &W_sel[j * C + i], 4);
            ptr += 4;
        }
    }

    fprintf(stderr, "[csp] Calibration complete: %zu bytes\n", state_size);

    free(C0); free(C1); free(C_comp); free(lambda); free(U); free(P);
    free(PC1); free(S1); free(D); free(B); free(W_full); free(W_sel); free(labels);

    return (cortex_calibration_result_t){
        .calibration_state = state,
        .state_size_bytes = (uint32_t)state_size,
        .state_version = 1
    };
}

/* ============================================================================
 * ABI v3 Runtime Functions
 * ============================================================================ */

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[csp] ERROR: ABI mismatch\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (!config->calibration_state) {
        fprintf(stderr, "[csp] ERROR: Calibration state required\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    csp_runtime_state_t *state = malloc(sizeof(csp_runtime_state_t));
    if (!state) return (cortex_init_result_t){NULL, 0, 0, 0};

    const uint8_t *bytes = (const uint8_t *)config->calibration_state;
    uint32_t C, n_components;

    memcpy(&C, bytes, 4); bytes += 4;
    memcpy(&n_components, bytes, 4); bytes += 4;

    if (C != config->channels) {
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    state->W = config->window_length_samples;
    state->C = C;
    state->n_components = n_components;

    state->W_filters = malloc(C * n_components * sizeof(float));
    if (!state->W_filters) {
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    memcpy(state->W_filters, bytes, C * n_components * sizeof(float));

    fprintf(stderr, "[csp] Loaded: C=%u, n_components=%u\n", C, n_components);

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = state->W,
        .output_channels = n_components,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    csp_runtime_state_t *state = (csp_runtime_state_t *)handle;
    const float *x = (const float *)input;
    float *y = (float *)output;

    /* y = x @ W (W is column-major: [n_components, C]) */
    for (uint32_t t = 0; t < state->W; t++) {
        for (uint32_t k = 0; k < state->n_components; k++) {
            double sum = 0.0;
            for (uint32_t c = 0; c < state->C; c++) {
                /* Column-major indexing: element (k, c) at index k + c * n_components */
                sum += (double)x[t * state->C + c] * state->W_filters[k + c * state->n_components];
            }
            y[t * state->n_components + k] = (float)sum;
        }
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    csp_runtime_state_t *state = (csp_runtime_state_t *)handle;
    free(state->W_filters);
    free(state);
}
