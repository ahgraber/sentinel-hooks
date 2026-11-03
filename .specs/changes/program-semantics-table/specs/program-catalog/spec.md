# Delta for Program Catalog

## ADDED Requirements

### Requirement: EveryArgumentOfACatalogedProgramHasAStatedEffect

For every program the catalog lists, the catalog SHALL state what the program does with each word it can receive: which words are options, which options take a value and in which form, and the effects of each value, each operand, and each option that acts without a value.

The effects are: reading a file, writing a file, deleting a file, changing a file's permissions, owner, or times, running a file, changing the directory or the root the program works in, replacing its environment, running a command line, running shell text, running code in another language, a plain value, and unknown.
A word MAY carry several effects.
A word whose role the sources do not settle SHALL be stated as unknown, never as a plain value.

The catalog SHALL hold no policy.
It states what a program does; whether that is refused, put to the user, or allowed is decided by the hooks that read it.

Where implementations of one program accept different options or give one option different meanings, the catalog SHALL state each implementation's grammar.

A program's hidden inputs SHALL be stated with the program: each environment variable and configuration file that changes what the program does without appearing on its command line, and what it can do: supply options, make the program run another program, name files the program opens, or change only how the program interprets or presents its data.

A program's implicit effects SHALL be stated with the program or the subcommand that has them: an effect on a place no word names, such as the repository state `git stash` and `git config set` write, the directory an archive extracts into when no member is named, and standard input read as program text by an interpreter given no script.

Serves: every-argument-has-a-stated-effect

#### Scenario: AnOptionThatRunsAProgram

- **GIVEN** a cataloged program with an option whose value is a program it runs, such as `rg --pre`
- **WHEN** the catalog entry for that program is read
- **THEN** that option's value carries the effect of running a file

#### Scenario: AnOptionThatActsWithoutAValue

- **GIVEN** a cataloged program with an option that deletes the files it finds, such as `find -delete`
- **WHEN** the catalog entry is read
- **THEN** that option carries the delete effect although it takes no value

#### Scenario: ImplementationsDisagree

- **GIVEN** a program whose GNU and BSD implementations parse one option differently, such as `sed -i`
- **WHEN** the catalog entry is read
- **THEN** it states each implementation's form of that option

#### Scenario: AnUndecidedRole

- **GIVEN** an option whose effect the program's documentation does not settle
- **WHEN** the catalog entry is read
- **THEN** the option's value is unknown, not a plain value

#### Scenario: AnEffectNoWordNames

- **GIVEN** the subcommands `git stash` and `git config set`
- **WHEN** the catalog entry for `git` is read
- **THEN** each carries a write of repository state, though no operand names it

#### Scenario: AnInterpreterGivenNoScript

- **GIVEN** an interpreter that is not a shell, such as `python3` or `node`
- **WHEN** the catalog entry is read
- **THEN** running it with no script operand, or with `-`, reads program text from standard input

#### Scenario: AHiddenInputThatRunsAProgram

- **GIVEN** a program whose environment can name a program it runs, such as `PAGER` or `PYTHONSTARTUP`
- **WHEN** the catalog entry is read
- **THEN** that hidden input is stated as one that runs a program, apart from inputs that change only presentation

### Requirement: AReadingKeepsEveryEffect

For any Bash segment whose program the catalog lists, the reading SHALL hold every effect the segment's words carry, each with its target and with the context it applies in: the directory a path resolves in, whether the outer shell or a nested shell expands it, and the environment the program runs with.
No effect SHALL be dropped because another effect of the same word or segment is more severe.

Where implementations of the program disagree on a command, the reading SHALL hold the effects of every implementation that accepts the command.
An implementation whose documentation shows that it rejects the command contributes no effects.
An implementation the catalog cannot settle the command for makes the reading incomplete, as `AnIncompleteReadingEndsRecognition` requires; so does a command every implementation rejects.

Where a mode or a subcommand selects a grammar, its grammar SHALL replace the parent's for the words it covers; an option that changes how operands are used SHALL add effects to the operands it names.

Each hook judges the effects its own policy covers, so an effect one hook ignores is still there for the hook that checks it.

Serves: every-argument-has-a-stated-effect, a-wrapper-read-once-holds-everywhere

#### Scenario: CodeAndAWriteInOneSegment

- **GIVEN** the segment `sed -i -e p /project/file`
- **WHEN** it is read
- **THEN** the reading holds both the sed code and a write of `/project/file`

#### Scenario: TwoImplementationsReadOneCommand

- **GIVEN** a segment that GNU and BSD `sed` parse into different effects
- **WHEN** it is read
- **THEN** the reading holds the effects of both

#### Scenario: AModeSelectsTheFileDirection

- **GIVEN** the segments `tar -xf /project/a.tar` and `tar -cf /project/a.tar /project/src`, run in `/project/work`
- **WHEN** each is read
- **THEN** the first reads `/project/a.tar` and writes beneath `/project/work`, and the second writes `/project/a.tar` and reads `/project/src`

#### Scenario: AGlobExpandedBeforeADirectoryChange

- **GIVEN** the segment `env -C /project/sub cat *.txt`
- **WHEN** it is read
- **THEN** the glob is expanded in the outer shell's directory and the read targets resolve in `/project/sub`

#### Scenario: AGlobExpandedInsideANestedShell

- **GIVEN** the segment `env -C /project/sub sh -c 'cat *.txt'`
- **WHEN** it is read
- **THEN** the glob is expanded in `/project/sub`

#### Scenario: AnOuterRedirectionBesideAChildOperand

- **GIVEN** the segment `env -C /project/sub cat input > output`, run in `/project`
- **WHEN** it is read
- **THEN** the read target is `/project/sub/input` and the write target is `/project/output`

#### Scenario: RepositoryStateIsNotADirectoryChange

- **GIVEN** the segment `git --git-dir=/project/meta --work-tree=/project/tree status`
- **WHEN** it is read
- **THEN** the reading locates repository state in `/project/meta` and the work tree in `/project/tree`, and neither changes the directory relative paths resolve in

#### Scenario: OneImplementationRejectsTheCommand

- **GIVEN** a command that GNU `head` accepts and whose option BSD `head` documents no form of, such as `head --lines=5 /project/input`
- **WHEN** it is read
- **THEN** the reading holds the GNU effects and is complete

#### Scenario: OneImplementationIsUnsettled

- **GIVEN** a command one implementation accepts and the catalog cannot settle for another
- **WHEN** it is read
- **THEN** the reading is incomplete and holds the effects of the implementation that accepts it

### Requirement: WrappersAreReadThrough

For any segment in which a cataloged program runs a command line it receives, the reading SHALL include the reading of that command line, in the context the wrapper gives it, to any depth up to a fixed bound, and whatever the order of the wrappers.
Shell text a program runs SHALL be lexed as `shell-lexing` requires and read the same way.

A program spelled with a path SHALL be read by the catalog entry for its base name, so `/usr/bin/sudo` and a nix store `sudo` are `sudo`.
The spelling SHALL be kept with the reading.

Serves: a-wrapper-read-once-holds-everywhere

#### Scenario: WrappersInAnyOrder

- **GIVEN** the segments `env sudo rm -rf /srv/data` and `sudo env rm -rf /srv/data`
- **WHEN** each is read
- **THEN** both readings hold a delete of `/srv/data`

#### Scenario: AValueLetterInsideACluster

- **GIVEN** the segment `sudo -nu root rm -rf /srv/data`
- **WHEN** it is read
- **THEN** `root` is the value of `-u`, and the reading holds a delete of `/srv/data`

#### Scenario: AnAbbreviatedLongOption

- **GIVEN** the segment `env --chd /project rm -rf /srv/data`, where `--chd` abbreviates an option the `env` entry lists
- **WHEN** it is read
- **THEN** recognition ends at `--chd`, and the rest of the segment is read as `AnIncompleteReadingEndsRecognition` requires

#### Scenario: AWordAfterTheEndOfOptions

- **GIVEN** the segment `rm -- -precious`
- **WHEN** it is read
- **THEN** the reading holds a delete of `-precious`

#### Scenario: APathSpelledProgram

- **GIVEN** the segment `/usr/bin/env rm -rf /srv/data`
- **WHEN** it is read
- **THEN** it is read as `env`, and the reading holds a delete of `/srv/data`

#### Scenario: ShellTextInsideAWrapper

- **GIVEN** the segment `nice bash -c 'rm -rf /srv/data'`
- **WHEN** it is read
- **THEN** the reading holds a delete of `/srv/data`

#### Scenario: NestingBeyondTheBound

- **GIVEN** a segment that nests command lines beyond the bound
- **WHEN** it is read
- **THEN** recognition ends at the bound, and no error decides the verdict

#### Scenario: ALauncherOfACommand

- **GIVEN** the segments `watch -x rm /project/f`, `uv run rm /project/f`, and `uvx --from ruff ruff check /project`
- **WHEN** each is read
- **THEN** the reading holds the command each runs, and the `uv` readings also hold the package installation `uv` performs

#### Scenario: AnUncatalogedChildOfAnInstaller

- **GIVEN** the segment `uvx some-tool`, where the catalog lists no `some-tool`
- **WHEN** it is read
- **THEN** the reading holds the package installation, and recognition ends for `some-tool`

#### Scenario: ProgramTextWithoutAFile

- **GIVEN** the segments `node -p '<code>'`, `deno eval '<code>'`, `uv run -`, and `uv run -m <module>`
- **WHEN** each is read
- **THEN** each reading holds program text the command runs, from its argument, from standard input, or from a module the text does not name

### Requirement: AnIncompleteReadingEndsRecognition

A reading SHALL end recognition for a program, rather than guess, when the segment holds a word whose role the catalog cannot settle: a program the catalog does not list, an invalid catalog entry, an option the entry does not list, an unresolvable word, an option that hands the program a command line the lexer has not split, or arguments a launcher builds at run time.

A reading that ends recognition SHALL keep every effect it found before it ended.
It SHALL also read the rest of the segment conservatively.
The program whose reading stopped counts as a program the segment may run.
So does every later word, and every part of a later word that a command-string wrapper would split out after removing the quoting and escaping it accepts, that names a cataloged program by base name.
Every path the segment names counts as a possible target of each effect such a program can have.
Where a program's entry is invalid, its possible effects are those the hooks recognized for it before the catalog, held apart from the catalog, so an invalid entry never removes a gate that exists today.
A hook that refuses or gates on an effect SHALL judge these possible effects as it judges known ones; a hook that admits a command SHALL NOT admit one whose reading ended.
Each hook SHALL treat a command whose recognition ended as it treats an unrecognized command under its own requirements, so no verdict is looser than the hook gives an unrecognized command today.

A launcher that builds the command it runs from its input or from files it finds, such as `xargs`, `find -exec`, and `parallel`, SHALL be read as building a command the text does not show, with the directory each built command runs in.
The words of that command the text does show SHALL be read as a command line, so the reading keeps the program it runs and every effect its shown words carry; only the generated words are unknown.

Serves: unknown-reads-as-dangerous

#### Scenario: AProgramWithNoEntry

- **GIVEN** a segment whose program the catalog does not list
- **WHEN** it is read
- **THEN** recognition ends for that program

#### Scenario: AnUnlistedOption

- **GIVEN** a segment that gives a cataloged program an option its entry does not list
- **WHEN** it is read
- **THEN** recognition ends for that program

#### Scenario: AnExpansionInTheOperands

- **GIVEN** the segment `sort /project/input $ARGS`
- **WHEN** it is read
- **THEN** recognition ends, because the expansion can be an option

#### Scenario: AnUnsplitCommandLine

- **GIVEN** the segment `env -S 'rm -rf /srv/data'`
- **WHEN** it is read
- **THEN** recognition ends

#### Scenario: ALauncherBuildsItsArguments

- **GIVEN** the segment `xargs -a /project/targets rm`
- **WHEN** it is read
- **THEN** the reading records a command built at run time that runs `rm`, and recognition ends for it

#### Scenario: AKnownChildBeforeGeneratedWords

- **GIVEN** the segment `xargs kubectl get pods,secrets`
- **WHEN** it is read
- **THEN** the reading holds `kubectl get` with the resource list it names, and the appended words are unknown

#### Scenario: AReplacementInsideAnArgument

- **GIVEN** the segment `xargs -I % cat /project/%.txt`
- **WHEN** it is read
- **THEN** the reading holds a `cat` whose read target is unknown, and not confined to `/project`, because the replacement can hold `..` and separators

#### Scenario: AChildRunInTheDirectoryItFinds

- **GIVEN** the segment `find /project -execdir rm -- '{}' ';'`
- **WHEN** it is read
- **THEN** the reading holds an `rm` of unknown targets beneath `/project`, each run in the directory that holds it

#### Scenario: AFixedTargetBesideGeneratedWords

- **GIVEN** the segment `xargs -a /project/targets rm -rf /srv/data`
- **WHEN** it is read
- **THEN** the reading holds a known delete of `/srv/data` and unknown generated words

#### Scenario: EffectsFoundBeforeTheEnd

- **GIVEN** the segment `sudo rm -rf /srv/data $EXTRA`
- **WHEN** it is read
- **THEN** recognition ends, and the reading still holds the privilege effect and the delete of `/srv/data`

#### Scenario: TheStoppedProgramItself

- **GIVEN** the segment `chmod --unlisted-option 000 /srv/data`
- **WHEN** it is read
- **THEN** recognition ends, and the reading holds `chmod` as a program the segment may run, with `/srv/data` as a possible permission target

#### Scenario: AnInvalidEntryForAProgramRecognizedToday

- **GIVEN** the catalog entry for `chmod` is invalid
- **WHEN** the segment `chmod 000 /srv/data` is read
- **THEN** the reading holds a possible permission change of `/srv/data`

#### Scenario: AQuotedNameInAnUnsplitCommandLine

- **GIVEN** the segment `env -S "'rm' -rf /srv/data"`
- **WHEN** it is read
- **THEN** the reading holds `rm` as a program the segment may run, with `/srv/data` as a possible delete target

#### Scenario: ADangerousProgramAfterTheStop

- **GIVEN** the segment `env -S 'rm -rf /srv/data'`
- **WHEN** it is read
- **THEN** recognition ends at `-S`, and the reading holds `rm` as a program the segment may run, with `/srv/data` as a possible delete target

### Requirement: ReadingACommandNeverFails

For any command text, any working directory, and any state of the catalog files, reading the command SHALL produce a reading and SHALL NOT end in an error.
A fault met while loading an entry or walking a segment SHALL end recognition for that segment, as `AnIncompleteReadingEndsRecognition` requires, and SHALL be reported as the entry or the word that caused it.

A hook that refuses a named class of command reaches `Block` on an error, under `hook-interface` `ErrorHandlingByDamagePotential`.
The privilege refusal reads every Bash command through this reading, so an error here would refuse every command it occurs on, on every agent; ending recognition instead leaves each hook's own rule for an incomplete reading in force.

Serves: unknown-reads-as-dangerous

#### Scenario: AnEntryOfTheWrongShape

- **GIVEN** an entry that parses as TOML but gives a field a value of the wrong type
- **WHEN** a command that reaches it is read
- **THEN** recognition ends for that program, the entry is reported as invalid, and no hook ends in an error

#### Scenario: AFaultWhileWalking

- **GIVEN** a fault raised while one segment is walked
- **WHEN** the command is read
- **THEN** recognition ends for that segment, the other segments are read as usual, and the reading is returned

#### Scenario: ArbitraryCommandText

- **GIVEN** command text drawn at random, including unbalanced quotes, control characters, and very long words
- **WHEN** it is read
- **THEN** a reading is returned

### Requirement: AnInvalidEntryDisablesOnlyItsProgram

An invalid catalog entry SHALL end recognition for its own program and for the names that reach it through an alias or a shared grammar, and for no other program.
An invalid alias index SHALL end recognition for every name that needs it, and for no program found by its own name.

A hook SHALL validate the entries a command reaches, as they are on disk when the hook runs, before it reads the command through them, so an entry edited during a session is judged by its edited form on the next tool call.
An invalid entry SHALL be reported, by name and with the defect, wherever the agent can show the report: at session start under `session-tool-checks`, in the reason of any refusal or ask on a command that reaches it, and as a warning on an allowed tool call that reaches it, on agents that show a warning on a tool call.

Serves: unknown-reads-as-dangerous

#### Scenario: OneEntryIsInvalid

- **GIVEN** the entry for `tar` does not parse
- **WHEN** a command runs `tar` and another runs `cat`
- **THEN** recognition ends for `tar`, and `cat` is read as before

#### Scenario: AnAliasReachesAnInvalidEntry

- **GIVEN** the entry for `tar` is invalid and `gtar` is its alias
- **WHEN** a command runs `gtar`
- **THEN** recognition ends for `gtar`

#### Scenario: AnInvalidEntryInARefusal

- **GIVEN** an invalid entry
- **WHEN** a command that reaches it is refused or asked about
- **THEN** the reason names the entry and its defect

#### Scenario: AnEntryCorruptedDuringASession

- **GIVEN** a session that started with a valid entry for `tar`, and an agent that shows a warning on a tool call
- **WHEN** the entry is made invalid and a later allowed command runs `tar`
- **THEN** the call proceeds with a warning that names the entry and its defect

#### Scenario: AnEntryRepairedDuringASession

- **GIVEN** an invalid entry for `tar`
- **WHEN** the entry is repaired and a later command runs `tar`
- **THEN** the command is read through the repaired entry

### Requirement: UncatalogedProgramsAreReported

The system SHALL report a program the catalog does not list wherever the agent can show the report without changing the verdict: as a warning on the tool call that runs it, on agents that show a warning on a tool call, and as a count with the location of a full list at session start.

Serves: unknown-reads-as-dangerous

#### Scenario: AnUncatalogedProgramOnAWarningAgent

- **GIVEN** an agent that shows a warning on a tool call
- **WHEN** a command runs a program the catalog does not list, and no hook refuses or asks
- **THEN** the call proceeds with a warning that names the program

#### Scenario: AnUncatalogedProgramOnAnAgentWithoutWarnings

- **GIVEN** an agent that cannot show a warning on a tool call
- **WHEN** a command runs a program the catalog does not list
- **THEN** the verdict is the one the hooks give that command without the report

### Requirement: TheCatalogIsCheckedAgainstItsUsers

The catalog SHALL be validated by the flake checks: every entry parses, uses only the fields and effects the schema defines, every alias and shared grammar reaches an existing entry, no chain of shared grammars returns to an entry it started from, no name is claimed by two entries, and no entry defines one option spelling twice for one implementation.

Every program the read classifier admits, every wrapper it treats as transparent, every program a refusal rule names, and every program in the catalog's declared coverage SHALL have a valid entry.
The declared coverage holds the privilege tools, wrappers, launchers, interpreters, and shells this change names.

Every entry SHALL carry, for each implementation it covers, the sources it was written from and the result of an independent verification against those sources.
An entry whose verification found an effect stated less severely than its sources show SHALL NOT pass until it is corrected.
A check that compares an entry with a program's own help output confirms the option spellings; it is not evidence of the effects.

Serves: every-argument-has-a-stated-effect, unknown-reads-as-dangerous

#### Scenario: AnEntryWithAnUndefinedEffect

- **GIVEN** an entry that names an effect the schema does not define
- **WHEN** the flake checks run
- **THEN** they fail and name the entry

#### Scenario: AnAdmittedProgramWithoutAnEntry

- **GIVEN** a program the read classifier admits
- **WHEN** the catalog has no valid entry for it
- **THEN** the flake checks fail

#### Scenario: SharedGrammarsThatFormACycle

- **GIVEN** two entries that each take their grammar from the other
- **WHEN** the flake checks run
- **THEN** they fail and name both entries

#### Scenario: AnEntryWithoutAVerificationRecord

- **GIVEN** an entry with no verification result for an implementation it covers
- **WHEN** the flake checks run
- **THEN** they fail and name the entry and the implementation

### Requirement: NoRecognitionIsLostInTheMove

Every program, option, and command form the hooks recognized before the catalog SHALL keep a valid entry that states it: the programs whose operands the ancestor gate judged, the write forms of the sensitive-path hook, the store commands, the privilege tools, the admitted readers with their refused and required options, the wrappers read through, the interpreters with their inline-code options, and the launchers.

For every command in the verdict cases recorded before the catalog, each hook SHALL reach the same verdict or a stricter one.
The exceptions are of two kinds, each named with its case.
A policy loosening is one the user approved: a read under `nice`, `caffeinate`, or `env` that `UnrecognizedCommandsAreGated` now admits, and an admitted utility spelled with a path in a trusted system directory.
A spec correction is a verdict that a misparse made stricter than a baseline requirement states, restored to that requirement, such as a run of an existing exec-through script under `bash -e`; each names the requirement it restores.
A looser verdict that is neither SHALL fail the check.

Serves: unknown-reads-as-dangerous

#### Scenario: AProgramRecognizedBeforeTheMove

- **GIVEN** a program the ancestor gate judged before the catalog, such as `ditto` or `setfacl`
- **WHEN** the flake checks run
- **THEN** they fail unless the catalog holds a valid entry that states its write, delete, or permission effects

#### Scenario: ARefusedOptionRecognizedBeforeTheMove

- **GIVEN** an option the read classifier refused before the catalog, such as `sort --compress-program`
- **WHEN** the admitted list is checked
- **THEN** the option is still refused

#### Scenario: AVerdictCaseFromBeforeTheMove

- **GIVEN** a command in the verdict cases recorded before the catalog
- **WHEN** each hook judges it
- **THEN** the verdict is the recorded one or stricter, unless the case is named as an approved loosening or as a spec correction with the requirement it restores

#### Scenario: ASpecCorrection

- **GIVEN** the recorded case `bash -e <existing exec-through script>`, gated before the catalog
- **WHEN** the tamper hook judges it
- **THEN** it proceeds, and the case is listed as a correction restoring `UnrecognizedCommandsAreGated`
