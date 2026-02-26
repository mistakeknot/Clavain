# Research: Write Root README.md

## Task
Replace the existing `/home/mk/projects/Demarch/README.md` with a new user-facing version.

## Analysis

### Current State
The current README.md at `/home/mk/projects/Demarch/README.md` is titled "Interverse" and is developer-focused — it lists all plugins, services, and infrastructure in table format with version numbers and GitHub links. It includes installation instructions for plugins via the marketplace CLI but lacks:
- A clear project description for newcomers
- Quick start instructions
- Architecture overview with layer descriptions
- Links to user guides
- Development lifecycle explanation

### Changes
The new README.md replaces the entire file with a user-facing version that:
1. Renames the title from "Interverse" to "Demarch" (the project's proper name)
2. Adds a one-line description of the platform
3. Provides a curl-based quick start installation
4. Lists what the user gets (Clavain, 33+ plugins, multi-model orchestration, sprint management)
5. Links to three guides: Power User, Full Setup, Contributing
6. Describes the 7-step development lifecycle (Discover through Ship)
7. Presents the 5-pillar architecture in a table with layer designations
8. Links to the interactive ecosystem diagram and marketplace
9. Documents the naming convention
10. Adds MIT license

### Key Findings
- The old README was an internal developer catalog; the new one is a public-facing project overview
- The CLAUDE.md file (which is the agent-facing doc) retains the detailed structure, naming conventions, and design decisions — nothing is lost
- The new README references docs that may not yet exist (guide-power-user.md, guide-full-setup.md, guide-contributing.md, install.sh) — these would need to be created separately
- The architecture table correctly maps pillars to layers per the project's established convention (L1=Core, L2=OS, L3=Apps)
