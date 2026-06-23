#!/usr/bin/env node

/**
 * Generate release notes using LLM analysis of git commits
 *
 * Usage: node generate-release-notes.js <previous-tag> <current-tag>
 */

import { execSync } from 'child_process';
import https from 'https';

// Configuration
const OPENROUTER_API_KEY = process.env.GH_ACTIONS_OPENAI_API_KEY;
const MODEL = 'anthropic/claude-sonnet-4.5';

/**
 * Get commits between two git references
 */
function getCommits(previousTag, currentTag) {
  const range = previousTag ? `${previousTag}..${currentTag}` : currentTag;

  try {
    const output = execSync(
      `git log ${range} --pretty=format:'%H|||%s|||%b|||%an|||%ae|||%aI%x00'`,
      { encoding: 'utf-8' }
    );

    if (!output.trim()) {
      return [];
    }

    return output.split('\0').filter(record => record.trim()).map(record => {
      const [hash, subject, ...rest] = record.trim().split('|||');

      if (!hash || !subject) {
        return null;
      }

      // The body may itself contain '|||' (unlikely but possible).
      // Fields after subject: body, authorName, authorEmail, date.
      // Pop the last three known fixed-format fields off the end.
      const date = rest.pop() || '';
      const authorEmail = rest.pop() || '';
      const authorName = rest.pop() || '';
      const body = rest.join('|||'); // rejoin in case body contained '|||'

      // Extract PR number if present (format: #123 or (#123))
      const prMatch = subject.match(/#(\d+)/);
      const prNumber = prMatch ? prMatch[1] : null;

      // Detect if this is a merge commit
      const isMerge = subject.toLowerCase().startsWith('merge pull request') ||
                      subject.toLowerCase().startsWith('merge branch');

      return {
        hash: hash.substring(0, 7),
        subject: subject.trim(),
        body: body.trim(),
        author: { name: authorName.trim(), email: authorEmail.trim() },
        date: date.trim(),
        prNumber,
        isMerge
      };
    }).filter(Boolean);
  } catch (error) {
    console.error('Error fetching commits:', error.message);
    console.error('Range:', range);
    return [];
  }
}

/**
 * Format commits for LLM prompt
 */
function formatCommitsForPrompt(commits) {
  return commits.map((commit, index) => {
    const bodySection = commit.body ? `\nDescription: ${commit.body}` : '';
    const prSection = commit.prNumber ? ` (PR #${commit.prNumber})` : '';
    const typeSection = commit.isMerge ? ' [MERGE]' : '';
    return `${index + 1}. [${commit.hash}]${typeSection} ${commit.subject}${prSection}${bodySection}`;
  }).join('\n\n');
}

/**
 * Call OpenRouter API to generate release notes
 */
function generateReleaseNotesWithLLM(commits) {
  return new Promise((resolve, reject) => {
    const formattedCommits = formatCommitsForPrompt(commits);

    const prompt = `You are a technical writer creating release notes for a software project. Analyze the following git commits and generate concise, user-friendly release notes.

Commits:
${formattedCommits}

Instructions:
- Group changes into logical categories (Features, Bug Fixes, Improvements, Documentation, etc.)
- Write in clear, user-focused language
- Highlight the most important changes
- Keep it concise but informative
- Use bullet points
- Use merge commits (marked with [MERGE]) and PR information to understand the context of changes
- Create semantic summaries - do not list individual PR numbers or commit hashes in the output
- Focus on what changed from a user perspective, not the implementation details
- Skip trivial changes like dependency updates or formatting
- Format as markdown
- Only output the release notes itself

Generate the release notes:`;

    const requestBody = JSON.stringify({
      model: MODEL,
      messages: [
        {
          role: 'user',
          content: prompt
        }
      ],
      temperature: 0.4
    });

    const options = {
      hostname: 'openrouter.ai',
      path: '/api/v1/chat/completions',
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(requestBody),
        'HTTP-Referer': 'foodsnap.eu',
        'X-Title': 'github actions'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const response = JSON.parse(data);

          if (response.error) {
            reject(new Error(`OpenRouter API error: ${response.error.message}`));
            return;
          }

          if (!response.choices || !response.choices[0]) {
            reject(new Error('Invalid response from OpenRouter API'));
            return;
          }

          const releaseNotes = response.choices[0].message.content;
          resolve(releaseNotes);
        } catch (error) {
          reject(new Error(`Failed to parse API response: ${error.message}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(new Error(`Request failed: ${error.message}`));
    });

    req.write(requestBody);
    req.end();
  });
}

/**
 * Generate fallback release notes without LLM
 */
function generateFallbackReleaseNotes(commits) {
  if (commits.length === 0) {
    return 'No changes in this release.';
  }

  let notes = '## Changes\n\n';
  commits.forEach(commit => {
    notes += `- ${commit.subject} (${commit.hash})\n`;
  });

  return notes;
}

/**
 * Main function
 */
async function main() {
  const [previousTag, currentTag] = process.argv.slice(2);

  if (!currentTag) {
    console.error('Usage: node generate-release-notes.js <previous-tag> <current-tag>');
    process.exit(1);
  }

  // Get commits
  const commits = getCommits(previousTag, currentTag);

  if (commits.length === 0) {
    console.log('No commits found, no release updates ...');
    return;
  }

  // Generate release notes
  try {
    if (!OPENROUTER_API_KEY) {
      console.warn('Warning: GH_ACTIONS_OPENAI_API_KEY not set, using fallback release notes');
      const notes = generateFallbackReleaseNotes(commits);
      console.log('\n' + notes);
      return;
    }

    const releaseNotes = await generateReleaseNotesWithLLM(commits);
    console.log(releaseNotes);

  } catch (error) {
    console.error('Error generating LLM release notes:', error.message);
    console.log('Falling back to simple release notes...');
    const notes = generateFallbackReleaseNotes(commits);
    console.log('\n' + notes);
  }
}

// Run
main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});