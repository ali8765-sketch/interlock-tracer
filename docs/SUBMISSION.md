# Devpost submission draft — Interlock Tracer

## Title
Interlock Tracer: Evidence paths for PLC downtime

## Tagline
Explain a blocked PLC output with deterministic logic and connected evidence in an offline Relate graph.

## Inspiration
Finding why a machine will not start can require tracing interlocks across several PLC programs. Existing snapshots and code often leave an engineer to piece together the chain manually. We wanted a clear, reviewable explanation that does not rely on a language model guessing the control logic.

## What it does
Interlock Tracer loads a limited Boolean Structured Text project and a snapshot into an embedded Relate graph. It explains which conditions contribute to a blocked output and shows paths from input tags through rungs to the output. It can find tags using German or English descriptions, show potentially affected downstream outputs, and compare dependencies across versions. When a missing value or unsupported expression prevents an answer, it reports the uncertainty explicitly.

## How we built it
We represent tags, gates, rungs and snapshots as connected graph nodes. Relate provides local graph storage, a full-text index and bounded shortest-path traversal. A deterministic Python evaluator handles AND, OR, NOT, cycles and unknown values. A self-contained Cytoscape.js view shows evidence paths. Read-only tools are available through MCP; an optional Claude client can explain their results. The demo runs offline without an API key.

## Challenges and what we learned
Cycles and self-holding logic require a clear snapshot-based rule to avoid infinite recursion. Boolean OR and NOT mean that simply listing all upstream tags does not explain the actual blocked state; evaluation must retain the relationships between contributing conditions. Unsupported logic must remain visible as unknown rather than being silently guessed.

## Evaluation and limitations
The repository includes automated tests and 30 synthetic example cases; these are not industrial validation. The project supports only a Boolean subset of Structured Text, has no live PLC connection and is not a certified safety system. The examples are synthetic and do not originate from a plant.

## Built with
Python, Relate (`relate-db`), Cypher, Cytoscape.js, MCP SDK, Anthropic SDK (optional).

## AI disclosure
Project notes describe earlier AI-assisted development with Claude Code; OpenAI Codex assisted subsequent implementation and review. Claude is optional at runtime and is instructed to explain tool results, not compute verdicts. Verify this disclosure against the hackathon's current rules and your actual tool usage before submission.

## GitHub topics
`relate` is required; `relate-neo4j-hackathon` is recommended by the [official rules](https://relate.devpost.com/rules). Keep the repository public with the required topic through judging and winner announcement.

## Video script, under two minutes
- **0:00–0:15:** A conveyor does not start. Its interlocks are spread across PLC programs; finding the cause is slow.
- **0:15–0:35:** Show the synthetic project, the Relate graph model and `itrace demo` running without an API key.
- **0:35–1:00:** Show the blocked M101 verdict, the input conditions and evidence paths in the offline viewer. Explain the conditions are examples, not repair instructions.
- **1:00–1:20:** Show guard-door impact and the v1.3 to v1.4 diff, including the new air-pressure dependency.
- **1:20–1:35:** Show the unresolved diverter logic returning INCOMPLETE instead of inventing an answer.
- **1:35–1:50:** Summarize the optional MCP/Claude explanation, tests and limitations. End with the repository and demo link once available.

Video, screenshots, a public repository and any deployed demo must still be created and verified before submission.
