/**
 * Aggregate Multi-Agent Code Review Feedback
 *
 * Collects review comments from multiple AI code review bots and aggregates
 * them into a structured format for Claude Code to analyze and fix.
 *
 * Expected bot usernames:
 * - cursor[bot] (Cursor BugBot)
 * - chatgpt-codex-connector[bot] (ChatGPT Codex)
 * - github-copilot[bot] (GitHub Copilot)
 * - copilot (alternative Copilot username)
 *
 * Usage:
 *   node aggregate-reviews.js <pr_number> <owner> <repo> <since_timestamp>
 */

const core = require('@actions/core');
const github = require('@actions/github');

// Known AI review bot usernames
const REVIEW_BOTS = [
  'cursor[bot]',
  'chatgpt-codex-connector[bot]',
  'github-copilot[bot]',
  'copilot',
  'github-actions[bot]'  // In case we trigger via Actions
];

async function aggregateReviews() {
  try {
    const token = process.env.GITHUB_TOKEN;
    const prNumber = parseInt(process.env.PR_NUMBER);
    const owner = process.env.REPO_OWNER;
    const repo = process.env.REPO_NAME;
    const sinceTimestamp = process.env.SINCE_TIMESTAMP;

    if (!token || !prNumber || !owner || !repo || !sinceTimestamp) {
      throw new Error('Missing required environment variables: GITHUB_TOKEN, PR_NUMBER, REPO_OWNER, REPO_NAME, SINCE_TIMESTAMP');
    }

    const octokit = github.getOctokit(token);

    console.log(`Collecting reviews for PR #${prNumber} since ${sinceTimestamp}`);

    // Fetch PR comments (issue comments)
    const {data: comments} = await octokit.rest.issues.listComments({
      owner,
      repo,
      issue_number: prNumber,
      since: sinceTimestamp
    });

    // Fetch PR review comments (line-level comments)
    const {data: reviewComments} = await octokit.rest.pulls.listReviewComments({
      owner,
      repo,
      pull_number: prNumber,
      since: sinceTimestamp
    });

    // Fetch PR reviews (overall reviews with state)
    const {data: reviews} = await octokit.rest.pulls.listReviews({
      owner,
      repo,
      pull_number: prNumber
    });

    // Filter for bot comments posted since trigger
    const sinceDate = new Date(sinceTimestamp);
    const botComments = comments.filter(c =>
      REVIEW_BOTS.includes(c.user.login) &&
      new Date(c.created_at) >= sinceDate
    );

    const botReviewComments = reviewComments.filter(c =>
      REVIEW_BOTS.includes(c.user.login) &&
      new Date(c.created_at) >= sinceDate
    );

    const botReviews = reviews.filter(r =>
      REVIEW_BOTS.includes(r.user.login) &&
      new Date(r.submitted_at) >= sinceDate
    );

    console.log(`Found ${botComments.length} bot comments, ${botReviewComments.length} review comments, ${botReviews.length} reviews`);

    // Aggregate by bot
    const aggregated = {};

    // Process general comments
    botComments.forEach(comment => {
      const botName = comment.user.login;
      if (!aggregated[botName]) {
        aggregated[botName] = {
          bot: botName,
          comments: [],
          reviewComments: [],
          reviews: []
        };
      }
      aggregated[botName].comments.push({
        id: comment.id,
        body: comment.body,
        created_at: comment.created_at,
        url: comment.html_url
      });
    });

    // Process line-level review comments
    botReviewComments.forEach(comment => {
      const botName = comment.user.login;
      if (!aggregated[botName]) {
        aggregated[botName] = {
          bot: botName,
          comments: [],
          reviewComments: [],
          reviews: []
        };
      }
      aggregated[botName].reviewComments.push({
        id: comment.id,
        body: comment.body,
        path: comment.path,
        line: comment.line || comment.original_line,
        created_at: comment.created_at,
        url: comment.html_url
      });
    });

    // Process overall reviews
    botReviews.forEach(review => {
      const botName = review.user.login;
      if (!aggregated[botName]) {
        aggregated[botName] = {
          bot: botName,
          comments: [],
          reviewComments: [],
          reviews: []
        };
      }
      aggregated[botName].reviews.push({
        id: review.id,
        state: review.state,  // APPROVED, CHANGES_REQUESTED, COMMENTED
        body: review.body,
        submitted_at: review.submitted_at,
        url: review.html_url
      });
    });

    // Format for Claude Code
    const formattedFeedback = {
      pr_number: prNumber,
      collected_at: new Date().toISOString(),
      since: sinceTimestamp,
      bots_responded: Object.keys(aggregated),
      total_issues: Object.values(aggregated).reduce((sum, bot) =>
        sum + bot.comments.length + bot.reviewComments.length + bot.reviews.length, 0),
      reviews: aggregated
    };

    // Generate human-readable summary for Claude
    let summary = `# Multi-Agent Code Review Feedback\n\n`;
    summary += `**PR**: #${prNumber}\n`;
    summary += `**Collected**: ${formattedFeedback.collected_at}\n`;
    summary += `**Bots Responded**: ${formattedFeedback.bots_responded.join(', ') || 'none'}\n`;
    summary += `**Total Issues**: ${formattedFeedback.total_issues}\n\n`;
    summary += `---\n\n`;

    if (formattedFeedback.total_issues === 0) {
      summary += `✅ No issues found by any review bots.\n`;
    } else {
      for (const [botName, botData] of Object.entries(aggregated)) {
        summary += `## ${botName}\n\n`;

        if (botData.reviews.length > 0) {
          summary += `### Overall Reviews\n\n`;
          botData.reviews.forEach(review => {
            summary += `- **${review.state}** (${review.submitted_at})\n`;
            if (review.body) {
              summary += `  ${review.body}\n`;
            }
            summary += `  [View](${review.url})\n\n`;
          });
        }

        if (botData.reviewComments.length > 0) {
          summary += `### Line-Level Comments\n\n`;
          botData.reviewComments.forEach(comment => {
            summary += `- **${comment.path}:${comment.line}**\n`;
            summary += `  ${comment.body}\n`;
            summary += `  [View](${comment.url})\n\n`;
          });
        }

        if (botData.comments.length > 0) {
          summary += `### General Comments\n\n`;
          botData.comments.forEach(comment => {
            summary += `${comment.body}\n\n`;
            summary += `[View](${comment.url})\n\n`;
          });
        }

        summary += `---\n\n`;
      }
    }

    // Output for GitHub Actions
    core.setOutput('feedback_json', JSON.stringify(formattedFeedback));
    core.setOutput('feedback_summary', summary);
    core.setOutput('has_issues', formattedFeedback.total_issues > 0 ? 'true' : 'false');
    core.setOutput('bot_count', formattedFeedback.bots_responded.length.toString());

    console.log('\n=== Aggregation Complete ===');
    console.log(`Bots responded: ${formattedFeedback.bots_responded.length}`);
    console.log(`Total issues: ${formattedFeedback.total_issues}`);
    console.log('\n=== Summary ===\n');
    console.log(summary);

  } catch (error) {
    core.setFailed(`Failed to aggregate reviews: ${error.message}`);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  aggregateReviews();
}

module.exports = { aggregateReviews };
