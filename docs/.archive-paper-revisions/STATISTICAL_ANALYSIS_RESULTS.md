# Statistical Significance Analysis Results

**Generated:** 2025-12-03
**Purpose:** Statistical validation for Idle Paradox finding

---

## Summary

All four BCI kernels show **highly significant** performance differences between idle and medium load conditions (p < 0.001), confirming the Idle Paradox is a systematic, reproducible phenomenon, not a measurement artifact.

---

## Results Table

| Kernel | n (Idle) | n (Medium) | t-statistic | p-value | Significance |
|--------|----------|------------|-------------|---------|--------------|
| bandpass_fir | 1,203 | 1,203 | **67.57** | < 0.001 | *** |
| car | 1,203 | 1,204 | **28.99** | 1.05×10⁻¹⁵⁸ | *** |
| goertzel | 1,203 | 1,203 | **37.56** | 1.33×10⁻²³⁸ | *** |
| notch_iir | 1,204 | 1,202 | **69.26** | < 0.001 | *** |

**Method:** Welch's t-test on log-transformed latencies (appropriate for log-normal distributions common in latency data).

**Significance codes:** *** p<0.001, ** p<0.01, * p<0.05, ns = not significant

---

## Interpretation

1. **Extremely high t-statistics** (28.99–69.26) indicate very large effect sizes
2. **Extremely low p-values** (< 10⁻¹⁵⁸) provide overwhelming evidence against the null hypothesis
3. **Large sample sizes** (n=1,200+ per condition) ensure statistical power
4. **Consistency across all kernels** rules out kernel-specific artifacts

The probability that these results occurred by chance is effectively zero. The Idle Paradox is **real, systematic, and reproducible**.

---

## LaTeX Snippet for Paper (Section 6.1)

Add this after presenting the 2.31× degradation finding:

```latex
Statistical significance was assessed using Welch's $t$-test on
log-transformed latencies (appropriate for log-normal distributions
common in latency data~\cite{li2014tales}). The idle-vs-medium
difference is statistically significant at $p < 0.001$ for all kernels:
\texttt{bandpass\_fir} ($t=67.6$, $p<0.001$),
\texttt{car} ($t=29.0$, $p<0.001$),
\texttt{goertzel} ($t=37.6$, $p<0.001$),
\texttt{notch\_iir} ($t=69.3$, $p<0.001$).
This confirms the Idle Paradox is a systematic, reproducible phenomenon,
not a measurement artifact.
```

---

## Plain Text Version for Paper

```
Statistical significance was assessed using Welch's t-test on
log-transformed latencies (appropriate for log-normal distributions
common in latency data [5]). The idle-vs-medium difference is
statistically significant at p < 0.001 for all kernels: bandpass_fir
(t=67.6, p<0.001), car (t=29.0, p<0.001), goertzel (t=37.6, p<0.001),
notch_iir (t=69.3, p<0.001). This confirms the Idle Paradox is a
systematic, reproducible phenomenon, not a measurement artifact.
```

---

## Additional Notes

### Why Log-Transform?

Latency distributions in computing systems are typically **log-normal** rather than normal:
- Mean > Median (right-skewed)
- Long tail of outliers due to OS scheduling, cache misses, etc.
- Multiplicative effects (e.g., 2× slowdown) rather than additive

Log-transforming makes the data approximately normal, satisfying t-test assumptions.

### Why Welch's t-test?

Welch's t-test doesn't assume equal variance between groups. Inspection of the data shows:
- Idle conditions have much higher variance (CV = 40-309%)
- Medium conditions have lower variance (CV = 29-126%)

Standard t-test would be invalid; Welch's test is appropriate.

### Sample Size Adequacy

With n=1,200+ per condition, we have:
- High statistical power to detect even small effects
- Robust to violations of normality (Central Limit Theorem)
- Tight confidence intervals on estimates

---

## Regeneration

To regenerate these results:

```bash
python3 scripts/calculate_statistical_significance.py
```

This script:
1. Loads telemetry data from validation runs
2. Applies log transformation
3. Computes Welch's t-test
4. Generates LaTeX snippets

---

## Citation

If citing this analysis methodology:

> Statistical significance assessed via Welch's t-test on log-transformed
> latencies following best practices for latency analysis in production
> systems [Li et al. 2014, "Tales of the Tail"].
