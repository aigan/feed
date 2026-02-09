# Backlog

## Metadata analysis pipeline

Redesign LLM-based video analysis into a multi-step pipeline. The current single-pass approach fails because:
- Video descriptions are ~95% promotional boilerplate (social links, sponsor blurbs)
- The LLM cannot reliably estimate its own uncertainty about extracted info

### Step 1: Split description into layers

Split the raw description text into three parts:
- **Channel info** — recurring boilerplate common across all videos from the channel
- **Series info** — recurring text shared by a subset of videos (e.g. series branding)
- **Video info** — the actual video-specific description (often zero bytes after stripping)

### Step 2: Extract info at each level

Process in order **channel → series → video**, so higher-level context is available when analyzing the next level:
1. Extract structured info from channel description
2. Extract structured info from series description, with channel context
3. Extract structured info from video description, with channel + series context

### Step 3: Verify extractions using logprobs

For each extracted field, ask the LLM a YES/NO question: "does the source text contain enough information to deduce this?" Use the **token logprob** on the YES/NO response as a real confidence signal, rather than asking the LLM to self-report confidence.

OpenAI API supports `logprobs: true` — check whether LangChain `ChatOpenAI` exposes this cleanly or if a direct API call is needed.

### Output

Each step produces named output files for traceability and incremental reruns.
