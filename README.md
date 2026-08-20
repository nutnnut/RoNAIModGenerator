# MAX SUSPECT Generator

A difficulty mod for Ready or Not that you *build*, instead of download.

Double-click **`MAX SUSPECT Generator.cmd`**. A page opens in your browser,
you pick how you want the game to play, and it writes a `.pak` straight into
your install. `Uninstall.cmd` removes it again.

Because it reads the difficulty data out of whatever game version you have
right now, **new maps and DLC are covered automatically** — after a patch,
open it and hit Build again. That is the whole point: the mods it replaces go
stale every time the game adds a map.

Requires Python 3.11 or newer ([python.org](https://www.python.org/downloads/),
tick *Add python.exe to PATH*). Nothing else to install, nothing leaves your
machine.

---

## The basics

Twelve presets to start from, then thirteen controls, grouped by who they
affect — Suspects, Civilians, SWAT, Environment:

| Control | Options |
|---|---|
| **Suspect count** | Multiplier (0.5x–3x or custom) · Flat range (your own min/max) · MAX |
| **Enemy accuracy** | Blind · Worse · Vanilla · Accurate · Aimbot |
| **Roaming suspects** | None · 0.5x · 1x · 2x · 3x · custom |
| **Civilian count** | same three modes, plus None |
| **Suspect health** | per-map or consistent, at 0.5x–2x or custom |
| **Suspects giving up** | Gives up easily · Vanilla · Fights to the end |
| **Civilians complying** | Complies quickly · Vanilla · Panics and runs |
| **Traps** | Removed · Vanilla · All maps, all types — with a 0.5x/1x/2x/custom count |
| **Less-lethal effectiveness** | Weak · Vanilla · Strong |
| **Suspect awareness** | Oblivious · Vanilla · Eagle-eyed |
| **Doors & keycards** | Wide open · Vanilla · Locked down |
| **Teammate health** | Fragile · Vanilla · Tanky |
| **Teammate skill** | Liability · Vanilla · Elite |

Every multiplier has a **Custom** button with its own number box, so nothing
is locked to the presets.

Multipliers scale what each map already has, so Hospital stays busier than Gas
Station. Flat range puts your own min/max on every map. MAX is a single number
with no range at all — min equals max, so the game cannot roll low.

**Preview changes** shows the before/after for all 30-odd maps without
touching the game. **Build & install** writes the pak.

## Advanced

Collapsed by default. Game folder, which difficulties to rewrite, install
location, pak name, what MAX means numerically, spawn placement, trap details,
and a free-form key editor plus per-map overrides.

The key editor merges two sources into one searchable list of ~305 settings.
The **values** come from the difficulty file installed right now, so they are
never stale. The **descriptions and categories** come from `ai_options.json`,
community documentation of the AI options, which covers keys the game's own
inline comments do not. Type to filter; each entry shows its category, its
stock value and what it does. Click the description to drop the stock value
into the box and edit from there.

Twenty-six documented settings are not written by the stock file at all —
`MaxRoamers`, `MinMeleeSuspects`, `MaxTrapsPlaceable`, the SWAT door-distance
keys, the perception half-angles. They are marked *not set by the stock file*
and are still offered, because the game reads them; they are simply appended
rather than rewritten.

This is also where the settings with no dedicated control live, such as
`HostageTakeAccuracyNerf` — how badly a suspect's aim suffers while holding a
human shield, 2.0 on Hard against 6.0 on Standard. How *often* a suspect grabs
a hostage is behaviour-tree logic, not config, so there is no knob for it.

After a build, `out\vanilla\HardDifficulty.ini` is the stock file with all its
original explanatory comments — that is your key reference. `out\generated\`
holds exactly what got packed.

---

## How this works, and why it works this way

Ready or Not defines difficulties as plain text in
`ReadyOrNot/Config/Difficulties/*.ini` inside its paks: an `[Info]` block, a
`[Global]` block of AI settings, and one section per map and mode
(`[RoN_Bank_BarricadedSuspects_Core]`). This tool reads those, rewrites the
values, and ships them back in a `_P` pak that takes priority over the
shipping ones.

It deliberately **rewrites the stock difficulties under their own names**
rather than adding a new one. A new difficulty only appears on maps whose
`LD_*.uasset` LevelData asset lists it, so adding one means hand-editing an
asset per map — which is precisely why the old *MAX SUSPECT* mod stopped
covering Ridgeline, Boat, Island, Rig, Fast Food, Meth Apartments, Bank, Pier
and Tower. Hard, Standard and Casual are already on every map, including maps
that do not exist yet.

### Spawn counts, and the trap in them

Most maps ship `UseSpawnGroups = true` plus per-group ranges:

```
MaxSuspects = 5
MinSuspects = 4
UseSpawnGroups = true
MinSuspects_Group0 = 3
MaxSuspects_Group0 = 5
```

With groups on, the **per-group** numbers decide how many suspects appear,
and a group can never produce more bodies than it owns spawn points. Ask a
group for far more than it has and the map spawns **nobody at all** — the
objective completes the moment you load in.

So whenever counts change, this tool sets `UseSpawnGroups = false` and drives
spawning from the flat per-map total instead, which is what working
high-count mods do. You can switch back to scaling the groups under Advanced
→ Spawn placement.

MAX defaults to **100 on every map**, min equal to max. The game clamps that
to the spawn points a map actually contains, so it means "everything this map
has". Vanilla runs 4–21; the highest-count mod that currently works ships a
flat 25–60. A build at 1000 with spawn groups left on produced empty maps, so
100 sits well clear of any map's capacity without going near the number that
failed — and it is one field in Advanced if you want to push it.

### Morale, and who gives up

Every AI carries a hidden morale value from 0.0 to 1.0, rolled at spawn
between a Min and a Max, and drained by shouting, flashbangs, tasers, seeing a
friend go down, doors coming in. When it bottoms out they surrender. The two
surrender controls set where suspects and civilians *start* on that scale,
along with fake-surrender odds and how long a suspect stays down.

They only touch faction-specific keys. The damage sources themselves —
`MoraleDamageRate`, `PlayerYellMorale.Damage`, `FlashMorale.Damage` and the
rest — hit suspects and civilians alike, so moving them from one side's
control would quietly move the other. Use the Advanced key editor for those.

The same caution applies to structural keys: forcing `SquadsEnabled = true`
on a map that ships it `false` can stop that map spawning too. The simple
controls never touch them.

### What the four extra controls move

**Less-lethal effectiveness** treats stun as the pool it is: `StunHealth` is
depleted by flashbangs, tasers, beanbags, pepperball and gas, and the AI drops
when it empties. Moving one source alone does nothing much, so the tiers move
the pool and every source together, along with the ninebanger accuracy penalty
and its recovery rate.

**Suspect awareness** is sight and hearing distance, cone width and memory —
`UnalertedSightRange`, `AlertedSightRange`, `GunShotHearingRange`,
`FlashlightPerceptionRange`, the forget timers and
`SuspectTrackLastKnownPositionTime`. This is deliberately separate from
accuracy: one decides whether they notice you, the other whether they hit you.

**Doors & keycards** sets `MaxLockedDoorsPercentage` and
`MaxOpenDoorsPercentage`. Locked down puts three quarters of the level behind
a breach and leaves nothing ajar. Keycard count is only raised, never lowered,
since objectives can depend on the cards.

**Teammate health** and **Teammate skill** are separate controls because
wanting tanky-but-useless teammates (or the reverse) is a common ask. Health is
`SwatHealth`; skill is the aim cone, the reaction times and how long they hold
a target's last known position.

Note that `SwatHealth` covers the **AI officers only**. Your own durability
comes from the armour you equip, which lives in the character assets rather
than in `Difficulty.ini`, so nothing here can change it. The difficulty files
do carry two player-facing knobs — `DamageCap` (the most damage a single hit
can deal) and `Bandages` — and both are reachable from the key editor.

### Did it actually load?

Every generated file writes its preset name into `DifficultySubtextKey`, so
the difficulty select screen shows e.g. *MaxSuspectGen: MAX SUSPECT* under
the difficulty name. If that subtitle is missing, the game is not reading
your pak — check that only one copy is installed and no other difficulty mod
is fighting it.

The **Vanilla** preset changes no values at all. If something breaks, build
that first: if the subtitle appears and the game plays normally, the pipeline
is fine and it is your numbers.

---

## Where you keep this folder

Anywhere. It finds Ready or Not through the Steam registry and
`libraryfolders.vdf`, so a second drive or a non-default library is fine, and
so is keeping the tool on your desktop. Override it under Advanced → Game
folder if you have several installs. `Uninstall.cmd` does the same lookup.

Output, downloads and your saved settings normally land next to the scripts,
so the whole thing stays one folder you can delete in one go. If that folder
will not take a write — unpacked into Program Files, run off a share, or
opened straight out of an archive viewer — they go to
`%LOCALAPPDATA%\MaxSuspectGen` instead. Nothing else is touched: no registry
keys, no PATH, no installer.

## Making a release zip

`python package.py` assembles `dist\MaxSuspectGenerator-1.0.zip`: the tool,
`oo2core.dll`, and a bundled copy of the embeddable Python runtime under
`runtime\python\`. That zip runs on a machine with no Python at all — unpack
it anywhere, double-click the launcher. About 11 MB.

| | |
|---|---|
| `python package.py` | everything bundled, ~11 MB, runs on a bare PC |
| `python package.py --no-python` | ~120 KB, needs Python 3.11+ installed |
| `python package.py --no-oodle` | leaves the DLL to be fetched on first run |

The launchers prefer `runtime\python\python.exe` when it is present and fall
back to `py` / `python` on PATH otherwise, so the same folder works either
way. `oo2core.dll` is the freely redistributable OodleUE build — the same one
FModel and repak use — and is only needed to read the game's own paks.

## Notes

- Disable other mods that ship `Config/Difficulties/*.ini` or `LD_*` level
  data — the app warns you about ones it can find.
- Multiplayer: the host's config is what counts.
- `MinFlees` / `MaxFlees` (how many AI bolt when they spot you) are general AI
  settings that cover suspects and civilians alike, so no faction control
  touches them. They are in the key editor.
- Only one copy should be installed. `Uninstall.cmd` clears every location.
- The generator only ever reads the shipping `pakchunk*-Windows.pak` files as
  its source, so its own output can never feed back into the next build.

## Command line

`build.cmd` runs a build from `config.toml` instead of the app — same engine,
one layer down. `python generate.py --list-maps` prints the map sections your
build exposes; `--dry-run` reports changes without writing.

## Files

| | |
|---|---|
| `app.py`, `ui.html` | the local web app |
| `presets.py` | presets and tiers — what each control maps to |
| `ai_options.json` | community documentation of the AI options |
| `generate.py` | the rewrite engine |
| `config.toml`, `build.cmd` | command-line path |
| `uninstall.py`, `Uninstall.cmd` | removal, from any location |
| `ronpak.py` | UE `.pak` v8–11 reader and writer |
| `uini.py` | comment-preserving Unreal `.ini` editor |
| `ronoodle.py` | Oodle binding; fetches `oo2core.dll` on first run |
| `gamedir.py` | Steam library detection |
| `paths.py` | picks a writable folder for output and settings |
| `package.py` | builds the distributable zip |
| `out\` | `vanilla\`, `generated\`, and the built pak |
