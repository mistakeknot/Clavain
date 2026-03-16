<!-- This document is a context cache. The JSONL store is authoritative.
     On resume, init_experiment reads the store and this document is rebuilt. -->
# Autoresearch: {campaign_name}

## Campaign
- **Metric:** {metric_name} ({direction})
- **Original Baseline:** {original_baseline}
- **Current Best:** {current_best} ({cumulative_delta} from baseline)
- **Experiments:** {completed}/{max}

## Recent Experiments (last 10)
| # | Hypothesis | Delta | Decision | Override? |
|---|-----------|-------|----------|-----------|

## Active Hypothesis
{current_hypothesis}

## Ideas Remaining
{count} ideas in autoresearch.ideas.md
