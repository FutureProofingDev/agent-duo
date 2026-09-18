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

- A plan reviewed before implementation starts.
- A second agent checking the changes and requesting corrections.
- Your project's checks run against the changes being reviewed.
- A GitHub pull request with the review, evidence and any checks still pending.

You may be asked to resolve a product decision or authorize access. Agent Duo
continues after plan approval unless you explicitly ask it to stop at planning.
The final pull request stays available for your decision; Agent Duo does not
merge or deploy it automatically.

## Update

Ask your agent:

```text
Update Agent Duo from https://github.com/FutureProofingDev/agent-duo
using INSTALL.md. Back up the installed version and verify the update.
```

Then start a new agent session. Updating the skill preserves existing run history.

## Want the details?

- [Installation instructions for agents](INSTALL.md)
- [Advanced setup, Orca, manual sessions and recovery](docs/advanced.md)
- [Workflow protocol](skill/references/protocol.md)
- [Contributing and testing](docs/advanced.md#repository-layout-and-contributing)

## License

Agent Duo is available under the [MIT License](LICENSE).
