# 🧭 Principles

The core tenets and philosophy behind winter — what it really is and why it exists.

### Remove the single-agent-flow bottleneck

Agentic development scales horizontally by adding more parallel agents. We enable parallel workstreams for complex applications through a workspace. We aim to enable a single agentic interface to manage teams of agents, as well as an array of agentic interfaces each working independently. The end goal: enable humans to orchestrate many agents working in many feature environments across many repositories.

#### Support local ephemeral environments

Shared development resources breed contention. Staging servers, single dev databases, and singleton local environments force humans and agents to take turns or step on each other. We believe each in-flight feature should be able to spin up its own runtime, hand it between humans and agents freely, and tear it down without residue. See [`winter-service-tmux`](https://github.com/paul-gross/winter-service-tmux) and [`winter-service-docker`](https://github.com/paul-gross/winter-service-docker).

### Separation of application, harness, workspace, and workflow

Application code should be about the product. The harness, the workspace, and the workflow are separate concerns and belong in their own areas, with a thin integration surface between them. We believe tools that require you to embed their conventions in your application don't leave space for innovation and change.

- **Application** — the code being built
- **Harness** — the interface to all of the context, progressively disclosed; the doorway to the library of knowledge, everything needed to manage the application
- **Workspace** — an extendable platform for agentic development, composed dynamically from modular extensions
- **Workflow** — the set of prompts (skills and subagents) that drive how an agent works: what the process is and what kind of reviews occur. Each developer has their own preference and taste, and autonomous cloud agents may have completely different workflows

#### Composable, reusable harnesses

Once these concerns are separated, harnesses compose. An application team can run a workspace focused on their own services with their own harness. An SRE might run a different workspace that pulls in many harnesses from many teams, driven by a completely different workflow — the harnesses become reusable building blocks. An architect can establish an architectural-governance harness that every application team is required to use. A harness engineer can establish a canon that guides all harness and context changes across the org. Breaking harness engineering down into composable modules — each owned by the people closest to it — is the path forward.

#### Workflows accept individual taste

Where harnesses compose, workflows stay personal. How an agent plans, commits, and reviews is a matter of individual taste, and winter doesn't force one on you. Each developer can bring their own workflow; an autonomous cloud agent can run a completely different one; teams can standardize where it helps and diverge where it doesn't. The workspace is the stable surface — the workflow on top of it is yours to choose.

Developers like to do things their own way, and they like to explore different ways to do things. They each bring different perspectives and weighted concerns. The variety and diversity of these workflows and perspectives lead to a better outcome.

### The workspace is a git repo

The workspace for a complex application should be shareable and versioned. Treat your workspace like cattle rather than a pet. Team members can slot into a workspace and work effectively from day one, and cloud agents can use the same workspace that developers use. Workspaces become the driving seat for change within an organization.

### Coordinate agentic work across many repositories

A polyrepo split is an implementation choice, not a unit of work. The natural unit is the feature — and features cross repos. We believe the workspace should let an agent (or a human) reason about a change as one coherent thing instead of N disconnected ones.

Agentic development now opens the door to massive changes across many repos, orchestrated by humans to enforce organization-wide policies. The workspace is what enables these changes and lets you apply large-scale initiatives.

### Pluggable, choose your tools or bring your own

Every team and every developer has opinions about how their agents plan, commit, and reason — and those opinions evolve fast. We believe the workspace should be a stable integration surface, and the harness and workflow should be swappable components chosen for the project at hand.

### Read-only views for humans, tools for agents

Enable agentic flows for development and operations while maximizing observability for the human. Provide the tools for agents to write code, create work items, manage pull requests, and more — while surfacing the information to humans via rich user interfaces with well-organized data and orchestration levers.

### Local agentic development over distributed agentic development

There is a lot of speed to be had working locally before we hit the bottleneck that requires distributed agentic development within cloud services. There is significant overhead and new issues to solve when moving to automated cloud agents. We believe empowering the agentic development process locally has undeniable efficiencies.

The future will contain both worlds. Developers can work optimally in local environments, orchestrating many agents to ideate and solve problems, while other tasks are delegated to cloud agents. In either case, the workspace makes each more efficient — and gives both a unified, single bootstrapping mechanism.
