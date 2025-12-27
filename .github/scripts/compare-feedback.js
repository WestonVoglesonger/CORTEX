/**
 * Compare Code Review Feedback Across Iterations
 *
 * Intelligently compares current bot feedback with previous iteration to
 * detect if new issues have been introduced or if all issues are resolved.
 *
 * This prevents infinite loops in the automated review-fix cycle.
 *
 * Returns:
 * - "no-issues": No bot feedback at all (clean!)
 * - "new-issues": Current feedback differs from previous (needs fixes)
 * - "same-issues": Feedback identical to previous iteration (loop detected - stop)
 *
 * Usage:
 *   node compare-feedback.js
 *
 * Environment Variables:
 * - CURRENT_FEEDBACK_JSON: JSON string from aggregate-reviews.js
 * - PREVIOUS_FEEDBACK_JSON: JSON string from previous iteration (empty if first run)
 */

const core = require('@actions/core');
const crypto = require('crypto');

/**
 * Normalize feedback for comparison
 * Removes timestamps, URLs, and other non-semantic differences
 */
function normalizeFeedback(feedbackJson) {
  if (!feedbackJson || feedbackJson === '{}' || feedbackJson === 'null') {
    return { normalized: '', hash: '', issue_count: 0 };
  }

  const feedback = typeof feedbackJson === 'string' ? JSON.parse(feedbackJson) : feedbackJson;

  // Extract just the semantic content (issue text, file paths, line numbers)
  const normalized = [];

  for (const [botName, botData] of Object.entries(feedback.reviews || {})) {
    // Process reviews
    botData.reviews?.forEach(review => {
      if (review.body) {
        normalized.push({
          bot: botName,
          type: 'review',
          state: review.state,
          content: review.body.trim()
        });
      }
    });

    // Process review comments (line-level)
    botData.reviewComments?.forEach(comment => {
      normalized.push({
        bot: botName,
        type: 'line_comment',
        file: comment.path,
        line: comment.line,
        content: comment.body.trim()
      });
    });

    // Process general comments
    botData.comments?.forEach(comment => {
      normalized.push({
        bot: botName,
        type: 'comment',
        content: comment.body.trim()
      });
    });
  }

  // Sort for consistent hashing
  normalized.sort((a, b) => {
    const aKey = `${a.bot}-${a.type}-${a.file || ''}-${a.line || ''}-${a.content}`;
    const bKey = `${b.bot}-${b.type}-${b.file || ''}-${b.line || ''}-${b.content}`;
    return aKey.localeCompare(bKey);
  });

  // Generate hash
  const contentString = JSON.stringify(normalized);
  const hash = crypto.createHash('sha256').update(contentString).digest('hex');

  return {
    normalized: contentString,
    hash: hash.substring(0, 16),  // Short hash for readability
    issue_count: normalized.length
  };
}

/**
 * Compare current and previous feedback
 */
function compareFeedback() {
  try {
    const currentFeedbackJson = process.env.CURRENT_FEEDBACK_JSON || '{}';
    const previousFeedbackJson = process.env.PREVIOUS_FEEDBACK_JSON || '{}';

    console.log('Comparing current and previous feedback...\n');

    // Normalize both
    const current = normalizeFeedback(currentFeedbackJson);
    const previous = normalizeFeedback(previousFeedbackJson);

    console.log(`Current: ${current.issue_count} issues (hash: ${current.hash})`);
    console.log(`Previous: ${previous.issue_count} issues (hash: ${previous.hash})`);

    // Determine outcome
    let result;
    let reason;

    if (current.issue_count === 0) {
      // No issues found - we're done!
      result = 'no-issues';
      reason = 'No bot feedback detected. PR is clean!';
    } else if (previous.issue_count === 0) {
      // First iteration with issues
      result = 'new-issues';
      reason = `First iteration: ${current.issue_count} issues found`;
    } else if (current.hash === previous.hash) {
      // Exact match - we're looping
      result = 'same-issues';
      reason = `Feedback identical to previous iteration (${current.issue_count} issues). Loop detected - stopping.`;
    } else if (current.issue_count === previous.issue_count) {
      // Same number but different content - could be different phrasing of same issues
      // Consider this "new issues" to be safe
      result = 'new-issues';
      reason = `Issue count unchanged (${current.issue_count}) but content differs. Treating as new issues.`;
    } else {
      // Different number of issues
      result = 'new-issues';
      const delta = current.issue_count - previous.issue_count;
      reason = `Issue count changed: ${previous.issue_count} → ${current.issue_count} (${delta > 0 ? '+' + delta : delta})`;
    }

    console.log(`\n=== Comparison Result ===`);
    console.log(`Outcome: ${result}`);
    console.log(`Reason: ${reason}\n`);

    // Output for GitHub Actions
    core.setOutput('result', result);
    core.setOutput('reason', reason);
    core.setOutput('current_hash', current.hash);
    core.setOutput('previous_hash', previous.hash);
    core.setOutput('current_count', current.issue_count.toString());
    core.setOutput('previous_count', previous.issue_count.toString());
    core.setOutput('should_fix', result === 'new-issues' ? 'true' : 'false');

    // Detailed comparison for debugging
    if (result === 'new-issues' && previous.issue_count > 0) {
      console.log('=== Detailed Comparison ===');
      console.log('Previous issues:');
      console.log(previous.normalized.substring(0, 500) + '...\n');
      console.log('Current issues:');
      console.log(current.normalized.substring(0, 500) + '...\n');
    }

  } catch (error) {
    core.setFailed(`Failed to compare feedback: ${error.message}`);
    console.error(error.stack);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  compareFeedback();
}

module.exports = { compareFeedback, normalizeFeedback };
