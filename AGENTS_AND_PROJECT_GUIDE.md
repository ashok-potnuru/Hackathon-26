# Agents And Project Guide

## Purpose

This document explains:

- what this project is trying to do
- why it uses multiple AI agents instead of one generic prompt
- what each agent is responsible for
- what has already been built in the codebase
- why those design decisions were made
- what the current implementation does today
- where the important files live

This file is meant to be a practical reference for anyone onboarding to the project.

---

## Project Summary

This project is an automated code-fix system for a two-repo platform:

- `API` repo: Node.js / Express
- `CMS` repo: PHP 8.2 / Laravel 10

The system takes a requirement, bug report, or ticket and tries to:

1. understand the requirement
2. decide which repo needs changes
3. locate the most relevant files using a code graph
4. inspect those files
5. generate a surgical fix
6. review that fix
7. optionally open a Draft PR

The goal is not just "generate code with AI". The goal is to create a safer, more structured, and more explainable pipeline for repository-aware code changes.

---

## Why We Built It This Way

### Why a multi-agent design is valuable here

This project uses a multi-agent approach because it gives the system several clear strengths:

- better file targeting through focused planning
- cleaner separation between planning, analysis, coding, and review
- stronger repo awareness when working across API and CMS
- better grounding in the real codebase through graph-based retrieval
- better attention to edge cases through a dedicated review stage
- more explainable outputs because each stage has a clear purpose

This is especially valuable for real repositories, and even more valuable when two connected repositories need to stay aligned.

### Why a multi-agent design is better here

This project splits the work into specialized stages so each agent has one clear job:

- one agent decides scope
- one agent finds relevant files
- one agent narrows relevant code
- one agent writes the patch
- one agent reviews the patch critically

This makes the system better in a few important ways:

- better focus: each agent solves a smaller problem
- better grounding: graph search and file retrieval happen before code generation
- better safety: the reviewer acts as a second opinion
- better explainability: every step has a visible output
- better cross-repo coordination: API and CMS changes can be planned in order

In short, the project is designed to reduce hallucination and increase controlled, auditable code generation.

---

## High-Level Architecture

The main execution flow looks like this:

1. intake provides the issue title and description
2. `MetaPlannerAgent` decides which repo or repos need work
3. for each repo, `PlannerAgent` extracts keywords and finds likely files
4. the system fetches file contents from GitHub
5. `ExplorerAgent` marks which files and line ranges are truly relevant
6. `CoderAgent` generates targeted edits
7. `ReviewerAgent` checks the proposed fix
8. the system can create a Draft PR

Top-level orchestration lives in:

- `core/stages/agent_runner.py`
- `scripts/agents_pipeline.py`

Design documentation lives in:

- `README.md`
- `MULTI_AGENT.md`
- `API.md`
- `CMS.md`

---

## Repositories Managed By The System

### API repo

- stack: Node.js 18 / Express.js
- graph source: `graph_api/graph.json`
- role: runtime API behavior, routes, services, DAL, platform settings, etc.

### CMS repo

- stack: PHP 8.2 / Laravel 10
- graph source: `graph_cms/graph.json`
- role: admin-side forms, data storage, Laravel logic, Livewire, Blade, and CMS-side configuration

The system supports requirements that affect:

- only API
- only CMS
- both API and CMS

That is one of the biggest reasons `MetaPlannerAgent` exists.

---

## Core Idea Behind The Agents

The agents are not random assistants. Each one is intentionally constrained.

That is a strength, not a limitation.

Instead of asking one model:

> "Please understand the whole issue, find the files, decide what matters, write code, and review yourself."

we split the work into smaller expert roles:

- planner
- explorer
- coder
- reviewer

This is closer to how good engineering teams work in practice:

- someone scopes the problem
- someone investigates the system
- someone implements the change
- someone reviews it skeptically

The system tries to recreate that workflow in a structured way.

---

## Agent Overview

### 1. BaseAgent

**File:** `core/agents/base_agent.py`

**What it does**

`BaseAgent` is the shared wrapper used by the other agents. It stores the configured LLM adapter and exposes a common `run_turn()` method.

**Why it exists**

Without this base class, each agent would need to create and manage LLM calls separately. That would duplicate logic and make the agent layer inconsistent.

**Why this is good**

- keeps the LLM interface consistent
- preserves the adapter abstraction
- makes it easier to swap providers like OpenAI, Claude, or Gemini
- keeps higher-level agent code clean

**What it does not do**

- it does not plan
- it does not write code
- it does not review

It is only the shared communication layer for the actual agents.

---

### 2. MetaPlannerAgent

**File:** `core/agents/meta_planner.py`

**Role**

This is the top-level routing and decomposition agent.

**What it reads**

- issue title
- issue description
- `API.md`
- `CMS.md`

**What it produces**

- ordered list of target repos
- repo-specific specification for API
- repo-specific specification for CMS
- search keywords for each repo
- shared context that both repos must agree on
- reasoning for the split

**What problem it solves**

A requirement may affect:

- only the API
- only the CMS
- both

If both are affected, the order matters. Example:

- CMS might create or store a field
- API might read and expose that field

In that case, CMS should be planned first because it is the data owner.

**Why this agent is strong**

- it prevents the rest of the system from working on the wrong repo
- it gives each downstream repo pipeline a focused subtask instead of the full original requirement
- it creates `shared_context`, which helps both repos use the same field names, defaults, and data structures
- it generates graph-friendly keywords early

**Why that is better than skipping this step**

Without `MetaPlannerAgent`, the later agents would need to figure out repo routing and implementation details at the same time. That makes mistakes much more likely, especially for cross-repo changes.

---

### 3. PlannerAgent

**File:** `core/agents/planner_agent.py`

**Role**

This agent converts a repo-specific requirement into likely code locations.

**Inputs**

- issue title
- focused description for one repo
- optional cross-repo context
- optional seed keywords from `MetaPlannerAgent`
- `GraphNavigator`

**Outputs**

- target files
- extracted keywords
- change type
- affected communities
- reasoning

**How it works**

1. uses the LLM to extract short runtime-oriented keywords
2. merges those with higher-signal seed keywords from `MetaPlannerAgent`
3. searches the repo graph for matching nodes
4. builds seed files from the best matches
5. expands to related files using graph BFS

**Why this agent is strong**

- it uses the graph, not just text guessing
- it avoids noisy files such as docs, tests, and migrations unless necessary
- it prefers runtime files
- it narrows the search space before expensive code reasoning happens

**Why that is better than a naive approach**

A naive AI system might search the whole repo or rely only on semantic intuition. This planner is stronger because it combines:

- LLM keyword extraction
- graph-based structural retrieval
- bounded related-file expansion

That gives the later agents much better context quality.

---

### 4. ExplorerAgent

**File:** `core/agents/explorer_agent.py`

**Role**

This is the read-only analysis agent.

**Inputs**

- issue title
- issue description
- code sections fetched from the repo

**Outputs**

- `must_change_files`
- `context_files`
- summary of the relevant area
- raw file analysis

**What makes it special**

Its prompt explicitly forbids it from proposing code changes. It is not a fixer. It is a reader and classifier.

**What it does**

- inspects candidate files
- identifies directly relevant line ranges
- decides whether a file must change or is only context
- narrows the code the coder will see

**Why this agent is strong**

- it separates investigation from implementation
- it prevents the coder from editing every fetched file
- it helps focus the code generation stage on the smallest useful context

**Why that is better than sending everything to the coder**

If the coder sees too much code, quality often drops:

- more noise
- more chances of over-editing
- more chances of unrelated changes

The explorer acts like a code analyst who says:

> "These files matter, these line ranges matter, and these other files are just helpful background."

That improves precision.

---

### 5. CoderAgent

**File:** `core/agents/coder_agent.py`

**Role**

This is the implementation agent.

**Inputs**

- issue title
- issue description
- explorer-selected code context
- optional reviewer feedback
- full base file contents
- repo type: `api` or `cms`

**Outputs**

- edited file contents
- reasoning
- confidence score
- suggested regression test
- raw LLM response
- edit list

**How it works**

The coder does not regenerate whole files by default. Instead, it is asked to produce **surgical edits**:

- file path
- exact `old_string`
- exact `new_string`

Then the Python implementation applies those edits to the original file content.

**Why this is strong**

- reduces giant uncontrolled rewrites
- makes changes easier to validate
- makes it easier to compare old vs new behavior
- lowers the chance of accidental formatting damage
- allows the system to reject hallucinated paths or non-matching edits

**Language awareness**

The coder uses different system prompts depending on repo type:

- API prompt for Node.js / Express
- CMS prompt for PHP / Laravel / Livewire / tenancy patterns

That matters because the coding conventions and common failure modes are different across those stacks.

**Why this is better than one generic code-writing prompt**

Generic prompts tend to write code that is technically plausible but not aligned with the stack's conventions. This agent is better because it is constrained to the specific repo environment and returns a patch-like structure rather than free-form code.

---

### 6. ReviewerAgent

**File:** `core/agents/reviewer_agent.py`

**Role**

This is the adversarial review agent.

**Inputs**

- original requirement
- original code
- proposed changed code

**Outputs**

- approved or not
- verdict: `PASS`, `FAIL`, or `PARTIAL`
- feedback
- issues list
- security status
- detailed check results

**What it checks**

- correctness
- security
- regression risk
- boundary values
- error handling
- concurrency
- style

**Why this agent is strong**

Its prompt is intentionally skeptical. It is told not to be impressed by a clean-looking fix. It is supposed to look for the missing 20 percent:

- edge cases
- unsafe assumptions
- hidden regressions
- weak validation
- incomplete logic

**Why that is better than trusting the coder**

Code generation and code review are different mental tasks. A model that just wrote the patch may be biased toward approving its own solution. A separate reviewer increases the chance of catching real problems before a PR is opened.

---

### 7. RepoRouter

**File:** `core/agents/repo_router.py`

**Role**

This is an older and simpler routing agent.

**What it does**

- decides whether the issue affects API, CMS, or both
- returns smaller repo-specific subtasks

**Current status**

This appears to be largely superseded by `MetaPlannerAgent`, which provides richer output:

- ordered repos
- repo-specific specs
- shared context
- keywords

**Why it still matters**

It shows the evolution of the system. The project started with a simpler routing concept and later matured into a more complete planning layer.

---

## Supporting Components That Make The Agents Work Well

The agents are not useful on their own. Several support pieces make them stronger.

### GraphNavigator

**File:** `core/utils/graph_navigator.py`

This is one of the most important non-agent components in the project.

**What it does**

- loads `graph_api/graph.json` or `graph_cms/graph.json`
- searches graph nodes using keywords
- finds related files by BFS
- can extract relevant line ranges from matched nodes

**Why it is valuable**

It grounds planning in code structure rather than only natural-language guesswork.

Instead of:

> "I think the settings code might be somewhere here"

the system can do:

> "These graph nodes match the keywords, these files own those nodes, and these nearby files are structurally related."

That makes the whole pipeline more reliable.

### Version control adapter

The pipeline fetches files from GitHub and can create branches, commit changes, and open Draft PRs.

This means the system is not just theoretical. It is designed to operate against real repositories.

### LLM adapter layer

The agent system is provider-agnostic. The code supports multiple LLM providers through adapters.

That is good because:

- models can be swapped
- costs can be controlled
- experimentation is easier
- the core business logic is not tied to one vendor

---

## What We Have Built In This Project

This project already includes the main building blocks of a multi-agent code-fix platform.

### 1. Agent framework

Implemented:

- common base agent abstraction
- specialized agents for planning, exploration, coding, and review
- top-level meta planner for cross-repo routing

### 2. Dual-repo support

Implemented:

- separate repo contexts for API and CMS
- separate graphs for API and CMS
- separate repo-specific prompts and planning

### 3. Graph-aware retrieval

Implemented:

- graph loading from committed JSON files
- keyword-based node search
- related-file expansion through adjacency

### 4. Code generation flow

Implemented:

- fetch file contents
- analyze relevant code
- generate surgical edits
- apply those edits to original file contents

### 5. Review stage

Implemented:

- independent review agent
- structured verdicts
- detailed safety checks

### 6. PR workflow

Implemented:

- branch creation
- file commits
- Draft PR creation
- PR body includes reasoning, changed files, confidence, and reviewer output

### 7. Test scripts

Implemented:

- per-agent live test scripts
- end-to-end multi-agent flow scripts
- unit tests for several components

---

## Why These Choices Make The Project Good

This project is stronger than a basic "AI coding bot" for several reasons.

### It is structured

The system has visible stages instead of hidden magic. That makes debugging and improvement easier.

### It is grounded

The planner is not guessing in a vacuum. It uses graph search and repo documentation.

### It is cross-repo aware

Many AI coding tools assume one repo and one task. This project can coordinate API and CMS work together.

### It is safer

The review stage and Draft PR flow add guardrails before anything is merged.

### It is adaptable

The adapter design means LLM, GitHub, issue tracker, and notification integrations can be swapped without changing core logic.

### It is closer to real engineering workflow

The pipeline resembles a team process:

- plan
- inspect
- implement
- review
- raise PR

That makes it more realistic and easier to trust.

---

## Current Execution Flow In Code Today

The currently wired runtime path is mainly:

- `core/stages/agent_runner.py`
- `scripts/agents_pipeline.py`

### What happens today

1. the issue enters the pipeline
2. `MetaPlannerAgent` decides the repo order and creates repo-specific specs
3. for each repo:
4. `PlannerAgent` chooses target files
5. file contents are fetched from GitHub
6. `ExplorerAgent` classifies the fetched code
7. `CoderAgent` proposes and applies edits
8. `ReviewerAgent` reviews the proposed changes
9. a Draft PR can be created

### Important note

The design docs in `MULTI_AGENT.md` describe an even richer architecture than the currently wired pipeline.

Examples of the design ambition:

- graph-based line filtering before exploration
- stronger retry loops from reviewer feedback back into coder
- broader file coverage in some cases

The current code already contains the core structure, but some parts of the documented design are more complete in the documentation than in the active orchestration path.

That is normal in evolving systems. It means the project has:

- a working implementation
- a clearer target architecture it is growing toward

---

## Why We Use Graph Files

The graph files:

- `graph_api/graph.json`
- `graph_cms/graph.json`

exist to make retrieval smarter.

### Why graphs help

In a real repo, keyword search alone is often weak:

- names can be broad
- relevant behavior may be split across files
- relationships between files matter

Graphs help because they model:

- file nodes
- code structure
- relationships between units
- communities or clusters in the codebase

That makes it easier to move from:

- "what words appear in the issue"

to:

- "what actual runtime files and neighbors are likely responsible"

This is one of the main technical ideas that makes the project more serious than a plain LLM wrapper.

---

## Why We Split API And CMS Context

The project maintains two dedicated context docs:

- `API.md`
- `CMS.md`

This is important because:

- the stacks are different
- the conventions are different
- the ownership of features is different
- the field creation path and field exposure path can live in different repos

By separating repo knowledge up front, the system can make better planning decisions.

This is especially useful for requirements like:

- "add a field in CMS forms and DB config"
- "expose the same field in the API response"

Without repo-specific context, an agent might mix those responsibilities.

---

## Why The Coder Uses Surgical Edits

The system does not ask the model to rewrite whole files unless necessary.

It asks for:

- exact path
- exact old string
- exact new string

This is a strong design choice because it:

- encourages minimal edits
- makes diff review easier
- reduces accidental changes
- makes patch application verifiable

For production-oriented AI workflows, this is usually much safer than free-form file regeneration.

---

## Why The Reviewer Matters So Much

A lot of AI systems stop after generating a patch.

This project adds a reviewer because generation alone is not enough. A patch can look good while still being:

- incomplete
- unsafe
- fragile
- inconsistent with the rest of the repo

The reviewer is valuable because it introduces healthy friction. It tries to fail the patch before the humans have to.

That does not replace human review, but it improves the quality of what reaches human review.

---

## Tradeoffs And Honest Notes

This project has many strong ideas, but it is also important to be honest about the tradeoffs.

### Strengths

- good modular design
- specialized agents
- cross-repo planning
- graph-backed file targeting
- provider abstraction
- PR automation

### Tradeoffs

- more moving parts than a simple bot
- more prompt and JSON parsing complexity
- depends on graph quality
- review quality still depends on model quality
- some documented behaviors are ahead of the currently wired implementation

These tradeoffs are normal for a system trying to be more reliable than a one-shot LLM workflow.

---

## Important Files

### Core agent files

- `core/agents/base_agent.py`
- `core/agents/meta_planner.py`
- `core/agents/planner_agent.py`
- `core/agents/explorer_agent.py`
- `core/agents/coder_agent.py`
- `core/agents/reviewer_agent.py`
- `core/agents/repo_router.py`

### Orchestration

- `core/stages/agent_runner.py`
- `scripts/agents_pipeline.py`

### Context and documentation

- `README.md`
- `MULTI_AGENT.md`
- `API.md`
- `CMS.md`

### Graph files

- `graph_api/graph.json`
- `graph_cms/graph.json`

### Test scripts

- `scripts/test_agents_live.py`
- `scripts/test_full_pipeline.py`

---

## Simple Mental Model

If you want to explain this project quickly to someone, you can say:

> This is a multi-agent AI system that reads a bug or feature request, decides which repo needs changes, uses graph-based retrieval to find the right files, narrows the important code, generates targeted edits, reviews those edits, and can open a Draft PR.

And if you want to explain why it is good:

> It is better than a single generic AI coder because it separates planning, retrieval, implementation, and review into specialized stages, which makes the system more grounded, safer, and easier to debug.

---

## Final Takeaway

What we have built is not just an AI chatbot for code. It is a structured engineering pipeline.

The important idea behind this project is:

- AI should not guess the whole solution in one jump
- AI should move through a controlled workflow
- each stage should reduce uncertainty for the next stage

That is why the agents exist.

Each agent removes a different kind of risk:

- `MetaPlannerAgent` removes scope confusion
- `PlannerAgent` removes file-selection guesswork
- `ExplorerAgent` removes irrelevant context
- `CoderAgent` turns analysis into a patch
- `ReviewerAgent` removes false confidence

Together, they make the system more useful for real repository work than a single unstructured prompt.
