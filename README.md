# Agent Duo

One agent builds. Another reviews. You describe what you want to change.

Agent Duo helps Codex and Claude Code take a feature or bug fix through planning,
implementation, tests and a reviewed pull request on GitHub.

## Install

**Ask your favorite coding agent to install Agent Duo from this repo.**
Copy this into Codex or Claude Code:

```text
Install Agent Duo from https://github.com/FutureProofingDev/agent-duo.
Read and follow INSTALL.md in that repository. Install it for the app
I'm using, preserve any previous installation, and verify that it works.
```

Your agent follows the [installation guide](INSTALL.md) and handles the technical
steps. It will tell you if it needs access to the repository or a missing tool.
When it finishes, open a new agent session to load the skill.

Use an agent that can access local files and run commands on your Mac or Linux
machine. A browser-only chat cannot install it on your computer.

## Try it

Open your project in Codex or Claude Code and ask:

```text
Use Agent Duo to add a search box to the currency selector.
Prepare the two agents, use this project's checks, and continue through
implementation and a reviewed pull request.
```

Replace the example with your own idea, bug description or GitHub issue link.
You can invoke the skill explicitly with `$agent-duo` in Codex or `/agent-duo`
in Claude Code. Your agent can choose the setup details from your project;
you do not need to supply internal commands or file paths.

Agent Duo needs two agent sessions. **Orca is optional:** with Orca, the launcher
can create both sessions automatically. Without it, your agent prepares the shared
workspace and prompts, then helps you open the second session. Automatic startup
outside Orca is not available yet.

## What you get

- A decision contract defining the outcome, constraints, pending assumptions and
  evidence needed to accept the work, followed by a reviewed plan.
- Handoffs tied to the exact code state, including uncommitted changes, with
  explicit responsibility for who can write during each phase.
- A second agent separating demonstrated defects, relevant uncertainties and
  optional preferences, with specific corrections for blocking findings.
- Your project's checks run against the changes being reviewed. Review rounds
  are bounded; unresolved findings escalate when limits are reached.
- A GitHub pull request with the review, evidence and any checks still pending.

You may be asked to resolve a product decision or authorize access. Agent Duo
continues after plan approval unless you explicitly ask it to stop at planning.
The final pull request stays available for your decision; Agent Duo does not
merge or deploy it automatically.

## Optional lesson suggestions

Agent Duo can use Jev through classifier.dev to help the reviewer prioritize
lessons learned in earlier runs. Ask your agent to **enable Jev lesson suggestions
for this project**. Enabling sends the task brief and active lesson patterns to
that external service. The full local memory remains available, and reviews keep
working when the service is unavailable. No API key is needed.

See [how suggestions work](skill/references/learning.md#optional-jev-lesson-suggestions).

## Update

Ask your agent:

```text
Update Agent Duo from https://github.com/FutureProofingDev/agent-duo
using INSTALL.md. Back up the installed version and verify the update.
```

Then start a new agent session. Updating the skill preserves existing run history.

This version uses **protocol 3**. Existing protocol 1 or 2 runs need their matching
older bundle to continue; the new controller will not migrate them automatically.
Keep the installation backup for those runs, or start a new run and revalidate
the evidence. See the [protocol reference](skill/references/protocol.md) for the
evidence boundaries and recovery rules.

## Want the details?

- [Installation instructions for agents](INSTALL.md)
- [Advanced setup, Orca, manual sessions and recovery](docs/advanced.md)
- [Workflow protocol](skill/references/protocol.md)
- [Contributing and testing](docs/advanced.md#repository-layout-and-contributing)

## License

Agent Duo is available under the [MIT License](LICENSE).
