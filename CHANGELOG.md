# Changelog

All notable changes to sts2-cli are documented here.

---

## Mar 23, 2026

### Added
- **Character & ascension positional args** — `play.py d 4` launches Defect at Ascension 4; character abbreviations `i/s/d/r/n` accepted (case-insensitive)
- **Colored map nodes** — Elite (magenta), Rest (green), Shop (yellow), Treasure/Ancient (orange), Event (blue); available paths are underlined
- **Boss name on map** — current act boss is shown above the map separator line
- **Shop descriptions** — cards, relics, and potions in the shop now show their description inline
- **Multi-card selection** — card select prompts show the required count range (e.g. `2-2`) and accept comma- or space-separated indices; invalid counts are rejected with a clear message
- **`map` command from any state** — typing `map` outside of `map_select` now derives reachable nodes from current position and renders the full map
- **zsh alias docs** — README now includes an optional `sts2` shortcut alias for macOS

### Changed
- **All interactive indices are now 1-based** — cards, enemies, potions, relics, bundles, rest options, event options, and map paths all start at `1` (previously `0`)
- **Updated help text and README** to reflect 1-based indices (`p1`, `c1`, `r1`, etc.)
- **`setup.sh` now enforces .NET 9+ and adapts to the installed version** — detects the SDK major version at startup, rejects versions below 9 with a clear error, and compiles the IL patcher against the detected framework (`net9.0`, `net10.0`, etc.); GodotStubs resolver path is now discovered dynamically instead of being hardcoded to `net9.0`
- **Event option vars** — card-type variable names (Attack, Skill, Power, etc.) are now resolved to their localized display string instead of a raw integer
- Refactored meta-command handling into a shared `_handle_meta()` helper

### Fixed
- Rest site **SMITH** now waits for the upgrade action to complete before transitioning to the map
- Rest site **HEAL** now waits for the heal action before forcing navigation to the map
- Potion use now correctly passes the engine's internal index regardless of display order

---

## Mar 22, 2026

### Added
- **Game logging and replay** — simulator writes structured logs for bug reproduction

### Fixed
- Self-targeting cards no longer fail when `target_index` is provided (BUG-022)
- Three additional simulator bugs resolved (BUG-005, BUG-007, BUG-013)
- Compact bridge mode added for AI agent use cases
- `GodotSharp` assembly resolution error in `setup.sh` IL patching step
- File lock error during `setup.sh` DLL patching on macOS

### Chore
- Added `.gitignore` entries for learning files, bug tracker, and temporary play scripts
- Random port selection in `sts2-cli-agent` skill to avoid conflicts
