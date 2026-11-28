# Proposal: sensitive-path-word-narrowing

Status: stub.
This change does not start until `program-semantics-table` is archived and the evidence named under "Entry condition" exists.
It has no delta specs, design, or tasks.

## Intent

`sensitive-path-blocking` `BlockBashReadFromZeroAccessPath` judges every word of a segment that runs a recognized reader by the strong rules, whatever the word is.
`grep -e .env /project/input` is refused, although `.env` there is a search pattern and the command reads only `/project/input`.
The broad check exists because a word-level reading could miss a word that names a file, and a credential read cannot be undone.

`program-semantics-table` types each argument by effect, so a hook could judge only the words a reader opens.
The user decided on 2026-10-16 to keep the broad check in that change, and to narrow it only if the narrower check is shown to keep false negatives minimal.

## User Stories

### Story: patterns-are-not-paths

As the operator of four agents, I want a search pattern, a format string, or another plain value that only looks like a credential path to stop being refused, so that searching for `.env` in source code does not cost a prompt or a refusal, while every word a reader opens as a file is still judged.

North star: "response matches risk"; a search for the text `.env` reads no credential.

## Entry condition

The narrowing starts only with evidence that it keeps false negatives minimal:

- Every word the broad check refuses today, across the verdict tables and a sample of real agent commands, is classified by the catalog as a file the reader opens or as a plain value, and every plain-value classification is confirmed against the program's documentation.
- A word whose role depends on parsing the catalog cannot settle (an unknown option, an implementation disagreement, an unresolvable word) stays under the broad check.
- A pattern that can name a file indirectly stays under the broad check: an option that reads patterns or arguments from a file (`grep -f`, `rg --file`, `xargs -a`), and a value a program later opens.
- The catalog rows for every admitted reader have passed their verification pass with no `effect-under` finding.

## Scope

**In scope:**

- Narrowing the strong-rule check from every word of a reader's segment to the words the reading types as files read, keeping the broad check wherever the reading is incomplete.
- Delta scenarios for each case the narrowing relaxes and each case it must keep.

**Out of scope:**

- The name rules, the declared block paths, and the sandbox and permission layers.
- Readers outside the admitted list.

## Open Questions

- Which sample of real agent commands is large enough to stand as evidence, and where it comes from.
