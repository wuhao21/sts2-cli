# STS2 Console Command Reference

- Generated on: `2026-04-07`
- Source: reflected from local `sts2.dll` via `dump_console_commands`
- Coverage: `39` commands
- Scope: this document describes the `console` bridge exposed by this workspace's `sts2-cli`, not a transcription of the game's GUI help overlay

## How to use it

- Raw game syntax: `fight SHRINKER_BEETLE_WEAK`
- In this `sts2-cli` workspace: `console fight SHRINKER_BEETLE_WEAK`
- All examples below use the CLI form: `console <command>`

## Risk levels

- `safe`: inspection, export, or local-path helpers with low gameplay risk
- `stateful`: changes the current run, combat, map, resources, or UI state
- `dangerous`: touches persistent progress, cloud saves, external services, or crash flows

## Practical notes

- Commands with `<id:string>` usually expect model IDs.
- If you need IDs, start with `console dump`.
- The bridge is confirmed working for: `gold`, `fight`, `event`, `room`, `card`, `relic`, `potion`, `upgrade`.
- `act` exists and exports correctly, but is not stable in the current headless bridge.

## Quick Index

| Command | Category | Risk | Syntax | Tested |
| --- | --- | --- | --- | --- |
| `act` | Flow and navigation | `stateful` | `<int|string: act>` | Tested, bridge unstable |
| `ancient` | Flow and navigation | `stateful` | `<id:string> <choice:string>` | Not tested |
| `event` | Flow and navigation | `stateful` | `<id:string>` | Tested |
| `fight` | Flow and navigation | `stateful` | `<id:string>` | Tested |
| `multiplayer` | Flow and navigation | `stateful` | `none` | Not tested |
| `room` | Flow and navigation | `stateful` | `<id:string>` | Tested |
| `travel` | Flow and navigation | `stateful` | `none` | Not tested |
| `power` | Combat and resources | `stateful` | `<id:string> <amount:int> <target-index:int>` | Not tested |
| `block` | Combat and resources | `stateful` | `<amount:int> <target-index:int>` | Not tested |
| `damage` | Combat and resources | `stateful` | `<amount:int> <target-index:int>` | Not tested |
| `die` | Combat and resources | `stateful` | `none` | Not tested |
| `draw` | Combat and resources | `stateful` | `<count:int>` | Not tested |
| `energy` | Combat and resources | `stateful` | `<amount:int>` | Not tested |
| `godmode` | Combat and resources | `stateful` | `none` | Not tested |
| `gold` | Combat and resources | `stateful` | `<amount:int>` | Tested |
| `heal` | Combat and resources | `stateful` | `<amount:int> [index:int]` | Not tested |
| `instant` | Combat and resources | `stateful` | `none` | Not tested |
| `kill` | Combat and resources | `stateful` | `<target-index:int>|'all'` | Not tested |
| `stars` | Combat and resources | `stateful` | `<amount:int>` | Not tested |
| `win` | Combat and resources | `stateful` | `none` | Not tested |
| `afflict` | Cards, relics, and potions | `stateful` | `<id:string> [amount:int] [hand-index:int]` | Not tested |
| `card` | Cards, relics, and potions | `stateful` | `<card-id:string> [pileName:string]` | Tested |
| `enchant` | Cards, relics, and potions | `stateful` | `<id:string> [amount:int] [hand-index:int]` | Not tested |
| `potion` | Cards, relics, and potions | `stateful` | `<id:string>` | Tested |
| `relic` | Cards, relics, and potions | `stateful` | `[add|remove] <relic-id:string>` | Tested |
| `remove_card` | Cards, relics, and potions | `stateful` | `<id:string> [pileName:string]` | Not tested |
| `upgrade` | Cards, relics, and potions | `stateful` | `<hand-index:int>` | Tested |
| `achievement` | Progress and unlocks | `dangerous` | `<operation:string> [id:string]` | Not tested |
| `unlock` | Progress and unlocks | `dangerous` | `<type:string>` | Not tested |
| `art` | Diagnostics and system | `safe` | `<type:string>` | Not tested |
| `cloud` | Diagnostics and system | `dangerous` | `delete` | Not tested |
| `dump` | Diagnostics and system | `safe` | `none` | Not tested |
| `getlogs` | Diagnostics and system | `safe` | `<name:string>` | Not tested |
| `leaderboard` | Diagnostics and system | `dangerous` | `[option:string] [name:string] <score:int> [count:int]` | Not tested |
| `log` | Diagnostics and system | `stateful` | `[type:string] <level:string>` | Not tested |
| `open` | Diagnostics and system | `safe` | `logs|saves|root|build-logs|loc-override` | Not tested |
| `log-history` | Diagnostics and system | `safe` | `none` | Not tested |
| `sentry` | Diagnostics and system | `dangerous` | `<test|message|exception|crash|status> [text]` | Not tested |
| `trailer` | Diagnostics and system | `stateful` | `none` | Not tested |

## Flow and Navigation

- `act <int|string: act>`: jump to an act or replace the current act. `Tested`: bridge unstable in the current headless runtime.
- `ancient <id:string> <choice:string>`: open an ancient event and immediately choose one option. Common IDs include `NEOW`, `OROBAS`, `PAEL`, `TEZCATARA`, `VAKUU`.
- `event <id:string>`: jump to a specific event. `Tested`: `console event AROMA_OF_CHAOS`.
- `fight <id:string>`: jump straight into a specific encounter. `Tested`: `console fight SHRINKER_BEETLE_WEAK`.
- `multiplayer`: open the multiplayer menu. The built-in description also mentions a `test` argument even though `Args` is empty in the exported metadata.
- `room <id:string>`: jump to a room type. Common values in the current bridge are `Monster`, `Elite`, `Boss`, `Treasure`, `Shop`, `Event`, `RestSite`, `Map`. `Tested`: `console room RestSite`.
- `travel`: enable unrestricted map travel.

## Combat and Resources

- `power <id:string> <amount:int> <target-index:int>`: apply a power to a target by combat index.
- `block <amount:int> <target-index:int>`: grant block to the player or a target. `0` is the player.
- `damage <amount:int> <target-index:int>`: damage a target or all enemies if no target is provided by the game-side command.
- `die`: immediately kill the current player.
- `draw <count:int>`: draw cards, mainly useful in combat.
- `energy <amount:int>`: add energy to the player.
- `godmode`: enable invulnerability.
- `gold <amount:int>`: manipulate player gold. `Tested`: `console gold 123` changed gold from `99` to `222`.
- `heal <amount:int> [index:int]`: heal the player, with an optional target index exposed by the game metadata.
- `instant`: enable instant mode to skip waits.
- `kill <target-index:int>|'all'`: kill one target, the first target by default, or all targets with `all`.
- `stars <amount:int>`: add stars to the player.
- `win`: immediately win the current combat.

## Cards, Relics, and Potions

- `afflict <id:string> [amount:int] [hand-index:int]`: apply an affliction to a card in hand.
- `card <card-id:string> [pileName:string]`: spawn a card into a pile, hand by default. Use screaming snake case such as `BODY_SLAM`. `Tested`: `console card BODY_SLAM hand` after starting combat.
- `enchant <id:string> [amount:int] [hand-index:int]`: enchant a card in hand.
- `potion <id:string>`: add a potion to the belt. Use screaming snake case such as `ENTROPIC_BREW`. `Tested`: `console potion ENTROPIC_BREW`.
- `relic [add|remove] <relic-id:string>`: add or remove a relic, with `add` as the default behavior. `Tested`: `console relic add ANCHOR`.
- `remove_card <id:string> [pileName:string]`: remove a card from the hand or deck.
- `upgrade <hand-index:int>`: upgrade the card at a hand position, where `0` is the left-most card. `Tested`: `console upgrade 0` in combat.

## Progress and Unlocks

- `achievement <operation:string> [id:string]`: unlock or revoke achievements. If no ID is supplied, the game description says it applies to all achievements. High risk for real profiles.
- `unlock <type:string>`: mark discovery or unlock progress for categories such as cards, potions, relics, monsters, events, epochs, ascensions, or `all`.

## Diagnostics and System

- `art <type:string>`: list content of a given type that is missing art. The built-in description calls out `affliction`, `card`, `enchantment`, `power`, and `relic`.
- `cloud delete`: delete Steam Cloud save files when running through Steam. High-risk external side effect.
- `dump`: print the model ID database to the console and logs. This is the best first step when you need valid `<id:string>` values.
- `getlogs <name:string>`: gather logs, zip them, and open the containing directory.
- `leaderboard [option:string] [name:string] <score:int> [count:int]`: upload scores or random leaderboard samples. External side effect.
- `log [type:string] <level:string>`: change log levels. The built-in description lists types such as `Generic`, `Network`, `Actions`, `GameSync`, `VisualSync`, and levels such as `VeryDebug`, `Load`, `Debug`, `Info`, `Warn`, `Error`.
- `open logs|saves|root|build-logs|loc-override`: open common local paths in the OS file browser.
- `log-history`: save command history and open the directory that contains it.
- `sentry <test|message|exception|crash|status> [text]`: exercise Sentry reporting. `crash confirm` can trigger a native crash and terminate the game.
- `trailer`: toggle the trailer/UI visibility mode controlled by number keys and `+`/`-`.

## Validated behavior in this workspace

- `gold`, `fight`, `event`, `room`, `card`, `relic`, `potion`, and `upgrade` have all been exercised through `python/play.py` via the `console` bridge.
- `act` is exported correctly but is still unstable in the current headless bridge.
- `dangerous` commands such as `cloud`, `leaderboard`, `sentry`, `achievement`, and `unlock` were intentionally documented without live testing.
