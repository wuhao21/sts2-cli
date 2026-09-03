#!/usr/bin/env python3
"""
sts2-cli interactive player — play Slay the Spire 2 in your terminal.

Usage:
    python3 play.py                    # Interactive mode (you play)
    python3 play.py --auto             # Auto-play with simple AI
    python3 play.py --seed myseed      # Fixed seed for reproducibility
    python3 play.py --character Silent  # Choose character
"""

import json
import subprocess
import sys
import os
import argparse
import random
from game_log import GameLogger


def _configure_stdio():
    """Keep Windows code pages from crashing on emoji/CJK output."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


_configure_stdio()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(ROOT, "src", "Sts2Headless", "Sts2Headless.csproj")
LIB_DIR = os.path.join(ROOT, "lib")
SAVE_DIR = os.path.join(ROOT, "saves")


def _find_dotnet():
    """Find .NET SDK binary."""
    candidates = [
        os.environ.get("DOTNET"),
        os.path.expanduser("~/.dotnet-arm64/dotnet"),
        os.path.expanduser("~/.dotnet/dotnet"),
        "dotnet",
    ]
    for p in candidates:
        if not p:
            continue
        try:
            r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None

DOTNET = _find_dotnet()


def _is_wsl():
    """Check if running inside WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _find_game_dir():
    """Auto-detect STS2 Steam install directory."""
    import platform
    system = platform.system()
    candidates = []
    if system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources")
        candidates = [
            os.path.join(base, "data_sts2_macos_arm64"),
            os.path.join(base, "data_sts2_macos_x86_64"),
        ]
    elif system == "Linux":
        if _is_wsl():
            # WSL: scan Windows drives for Steam install
            for drv in ["/mnt/c", "/mnt/d", "/mnt/e", "/mnt/f", "/mnt/g"]:
                for steam in [
                    f"{drv}/Program Files (x86)/Steam",
                    f"{drv}/Program Files/Steam",
                    f"{drv}/SteamLibrary",
                    f"{drv}/Games/Steam",
                    f"{drv}/Steam",
                ]:
                    d = f"{steam}/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64"
                    candidates.append(d)
        # Native Linux Steam
        for steam in ["~/.steam/steam", "~/.local/share/Steam"]:
            candidates.append(os.path.expanduser(f"{steam}/steamapps/common/Slay the Spire 2"))
    elif system == "Windows":
        candidates = [r"C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2"]

    for d in candidates:
        if os.path.isdir(d):
            return d
    return None


def _copy_dlls(game_dir):
    """Copy required DLLs from game directory to lib/."""
    os.makedirs(LIB_DIR, exist_ok=True)
    dlls = [
        "sts2.dll", "SmartFormat.dll", "SmartFormat.ZString.dll",
        "Sentry.dll", "Steamworks.NET.dll", "MonoMod.Backports.dll",
        "MonoMod.ILHelpers.dll", "0Harmony.dll", "System.IO.Hashing.dll",
    ]
    import shutil
    for dll in dlls:
        src = os.path.join(game_dir, dll)
        dst = os.path.join(LIB_DIR, dll)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  ✓ {dll}")
        else:
            # Search subdirectories
            for root_d, _, files in os.walk(game_dir):
                if dll in files:
                    shutil.copy2(os.path.join(root_d, dll), dst)
                    print(f"  ✓ {dll}")
                    break
            else:
                print(f"  ✗ {dll} not found")

    # Backup original sts2.dll
    sts2 = os.path.join(LIB_DIR, "sts2.dll")
    backup = os.path.join(LIB_DIR, "sts2.dll.original")
    if os.path.isfile(sts2) and not os.path.isfile(backup):
        shutil.copy2(sts2, backup)


def _patch_dll():
    """Apply IL patches to sts2.dll using setup.sh (requires Mono.Cecil via dotnet)."""
    setup_sh = os.path.join(ROOT, "setup.sh")
    if not os.path.isfile(setup_sh):
        print("  ⚠ setup.sh not found, skipping IL patch")
        return
    # Run just the patching part via setup.sh
    subprocess.run(["bash", setup_sh], cwd=ROOT)


def _build():
    """Build the C# project."""
    if not DOTNET:
        return False
    r = subprocess.run([DOTNET, "build", PROJECT], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def ensure_setup():
    """Check that everything is ready to run. Auto-setup if needed."""
    issues = []

    # Check .NET SDK
    if not DOTNET:
        print("❌ .NET SDK not found.")
        print("   Install .NET 9+ from https://dotnet.microsoft.com/download")
        sys.exit(1)

    # Check lib/sts2.dll exists
    sts2_dll = os.path.join(LIB_DIR, "sts2.dll")
    if not os.path.isfile(sts2_dll):
        print("📦 Game DLLs not found. Running first-time setup...")
        game_dir = _find_game_dir()
        if not game_dir:
            print("❌ Could not find Slay the Spire 2 installation.")
            print("   Install the game via Steam, then run again.")
            print("   Or run: ./setup.sh /path/to/game/data")
            sys.exit(1)
        print(f"  Found game at: {game_dir}")
        _copy_dlls(game_dir)
        if not os.path.isfile(sts2_dll):
            print("❌ Failed to copy sts2.dll")
            sys.exit(1)

    # Set STS2_GAME_DIR env var for runtime DLL resolution (point to lib/ where DLLs were copied)
    if "STS2_GAME_DIR" not in os.environ:
        os.environ["STS2_GAME_DIR"] = LIB_DIR

    # Check if built
    exe_dir = os.path.join(ROOT, "src", "Sts2Headless", "bin", "Debug", "net9.0")
    exe = os.path.join(exe_dir, "Sts2Headless.dll")
    if not os.path.isfile(exe) or os.path.getmtime(sts2_dll) > os.path.getmtime(exe):
        print("🏗️  Building...")
        if not _build():
            print("❌ Build failed. Try: ./setup.sh")
            sys.exit(1)
        print("  ✓ Build succeeded")

# Language setting (set by --lang flag)
LANG = "zh"  # "en", "zh", or "both"

# ─── Native save file support ───

def _find_native_save_dir():
    """Auto-detect the game's save directory."""
    import platform, glob as globmod
    system = platform.system()
    patterns = []
    if system == "Darwin":
        patterns = [
            os.path.expanduser("~/Library/Application Support/SlayTheSpire2/steam/*/profile*/saves"),
        ]
    elif system == "Linux":
        patterns = [
            os.path.expanduser("~/.local/share/SlayTheSpire2/steam/*/profile*/saves"),
            os.path.expanduser("~/.config/unity3d/MegaCrit/Slay the Spire 2/steam/*/profile*/saves"),
        ]
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        patterns = [
            os.path.join(appdata, "SlayTheSpire2", "steam", "*", "profile*", "saves"),
            os.path.join(localappdata, "SlayTheSpire2", "steam", "*", "profile*", "saves"),
        ]
    for pat in patterns:
        matches = globmod.glob(pat)
        for d in matches:
            if os.path.isfile(os.path.join(d, "current_run.save")):
                return d
        if matches:
            return matches[0]
    return None

def _id_to_name(model_id):
    """Convert model ID like 'CARD.STRIKE_NECROBINDER' to readable name."""
    if not model_id:
        return "?"
    parts = model_id.split(".", 1)
    name = parts[-1] if len(parts) > 1 else model_id
    return name.replace("_", " ").title()

def show_native_save(save_path):
    """Parse and display a native current_run.save file."""
    try:
        with open(save_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{t('Error:','错误:')} Save file is not valid JSON: {save_path}")
        print(f"  {e}")
        sys.exit(1)

    print(f"\n{'═' * 60}")
    print(f"  {t('Native Save File', '游戏原生存档')}")
    print(f"  {save_path}")
    print(f"{'═' * 60}")
    seed = data.get("rng", {}).get("seed", "?")
    ascension = data.get("ascension", 0)
    act_idx = data.get("current_act_index", 0)
    acts = data.get("acts", [])
    act_name = _id_to_name(acts[act_idx]["id"]) if act_idx < len(acts) else "?"
    run_time = data.get("run_time", 0)
    run_min = run_time // 60
    run_sec = run_time % 60

    print(f"\n  {t('Seed','种子')}: {seed}")
    print(f"  {t('Ascension','攀升')}: {ascension}")
    print(f"  {t('Act','幕')}: {act_idx + 1} ({act_name})")
    print(f"  {t('Time','时间')}: {run_min}m{run_sec:02d}s")
    print(f"  Schema: v{data.get('schema_version','?')}")
    room = data.get("pre_finished_room", {})
    if room:
        room_type = room.get("room_type", "?")
        enc = room.get("encounter_id") or room.get("event_id") or ""
        room_type_display = t(room_type, ROOM_TYPE_ZH.get(room_type, room_type))
        print(f"  {t('Room','当前房间')}: {room_type_display}" + (f" ({_id_to_name(enc)})" if enc else ""))

    visited = data.get("visited_map_coords", [])
    if visited:
        print(f"  {t('Map','地图')}: {t('Floor','层')} {len(visited)} ({len(visited)} {t('nodes visited','个节点已访问')})")

    for player in data.get("players", []):
        char_name = _id_to_name(player.get("character_id", "?"))
        hp = player.get("current_hp", 0)
        max_hp = player.get("max_hp", 0)
        gold = player.get("gold", 0)
        energy = player.get("max_energy", 3)

        print(f"\n  {'─' * 50}")
        print(f"  {char_name}  HP: {hp}/{max_hp}  {t('Gold','金币')}: {gold}  {t('Energy','能量')}: {energy}")

        deck = player.get("deck", [])
        print(f"\n  {t('Deck','牌组')} ({len(deck)}):")
        card_counts = {}
        for card in deck:
            cid = _id_to_name(card.get("id", "?"))
            up = card.get("current_upgrade_level", 0)
            key = f"{cid}{'+'*up if up else ''}"
            card_counts[key] = card_counts.get(key, 0) + 1
        for name, cnt in sorted(card_counts.items()):
            print(f"    • {name}" + (f" x{cnt}" if cnt > 1 else ""))

        relics = player.get("relics", [])
        if relics:
            print(f"\n  {t('Relics','遗物')} ({len(relics)}):")
            for r in relics:
                print(f"    🔶 {_id_to_name(r.get('id', '?'))}")

        potions = player.get("potions", [])
        if potions:
            print(f"\n  {t('Potions','药水')} ({len(potions)}):")
            for p in potions:
                print(f"    🧪 [{p.get('slot_index', '?')}] {_id_to_name(p.get('id', '?'))}")

    if acts:
        print(f"\n  {'─' * 50}")
        print(f"  {t('Acts summary','幕章概览')}:")
        for i, act in enumerate(acts):
            act_id = _id_to_name(act.get("id", "?"))
            rooms_data = act.get("rooms", {})
            boss = _id_to_name(rooms_data.get("boss_id", ""))
            normals = rooms_data.get("normal_encounters_visited", 0)
            elites = rooms_data.get("elite_encounters_visited", 0)
            events = rooms_data.get("events_visited", 0)
            bosses = rooms_data.get("boss_encounters_visited", 0)
            marker = " ◀" if i == act_idx else ""
            print(f"    {t('Act','幕')} {i+1}: {act_id}  Boss: {boss}  "
                  f"[{t('M','怪')}{normals} {t('E','英')}{elites} {t('?','事')}{events} B{bosses}]{marker}")

    print(f"\n{'═' * 60}\n")

# ─── Display helpers ───

def n(obj):
    """Extract display name."""
    return str(obj) if obj is not None else "?"

def short_n(obj):
    """Short name only."""
    return str(obj) if obj is not None else "?"

def desc(obj):
    """Extract description, strip BBCode tags, clean SmartFormat vars."""
    if obj and isinstance(obj, str):
        import re
        text = obj
        text = re.sub(r'\[/?[^\]]+\]', '', text)  # strip BBCode [tags]

        # Handle SmartFormat expressions:
        # {IfUpgraded:show:text1|text2} → text2 (non-upgraded default)
        # {InCombat:text1|text2} → text1 (show combat version)
        # {energyPrefix:energyIcons(1)} → [E] (energy symbol)
        # {Stars:starIcons()} → [S] (star symbol)
        # {VarName:diff()} → [VarName] (simple var)
        # {VarName:choose(a|b)} → [VarName]

        def smart_replace(m):
            full = m.group(1)
            # Handle conditional: {IfUpgraded:show:textA|textB}
            if full.startswith("IfUpgraded:show:"):
                parts = full[len("IfUpgraded:show:"):].split("|")
                return parts[1] if len(parts) > 1 else parts[0]  # show non-upgraded
            if full.startswith("IfUpgraded:"):
                parts = full[len("IfUpgraded:"):].split("|")
                return parts[1] if len(parts) > 1 else parts[0]
            # {InCombat:text|alt} → show combat text
            if full.startswith("InCombat:"):
                parts = full[len("InCombat:"):].split("|")
                return parts[0].lstrip("\n")  # show combat version
            # Energy icons: {Energy:energyIcons()} → [Energy]能量
            if "energyIcons" in full:
                var = full.split(":")[0]
                return f"[{var}]{t('E','能量')}"
            # Star icons: {Stars:starIcons()} → [Stars]⭐
            if "starIcons" in full:
                var = full.split(":")[0]
                return f"[{var}]⭐"
            # Plural: {Cards:plural:card|cards} → card/cards based on value
            if ":plural:" in full:
                parts = full.split(":")
                var = parts[0]
                plural_parts = ":".join(parts[2:]).split("|")
                return f"[{var}:{plural_parts[0]}|{plural_parts[1] if len(plural_parts) > 1 else plural_parts[0]}]"
            # Conditional: {IsMultiplayer:textA|textB} → textB (single player)
            if ":" in full and "|" in full:
                parts_after = ":".join(full.split(":")[1:]).split("|")
                return parts_after[-1]  # take the false/last branch
            # Simple var with format: {Damage:diff()} → [Damage]
            var = full.split(":")[0]
            return f"[{var}]"

        # Process from innermost braces outward (handle nesting)
        for _ in range(3):  # max 3 nesting levels
            text = re.sub(r'\{([^{}]+)\}', smart_replace, text)
        return text.strip()
    return ""

COLORS = {
    "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
    "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
    "bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m",
}

def c(text, color):
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"

def bar(current, maximum, width=20):
    filled = int(current / max(maximum, 1) * width)
    return c("█" * filled, "red") + c("░" * (width - filled), "dim")

def t(en, zh=None):
    """Translate UI string based on LANG setting."""
    if zh is None:
        return en
    if LANG == "en":
        return en
    if LANG == "both":
        return f"{en} / {zh}"
    return zh

# Card rarities — keys match sts2 CardRarity.ToString(); ZHS from localization_zhs/gameplay_ui.json CARD_RARITY.*
RARITY_ZH = {
    "Basic": "基础",
    "Common": "普通",
    "Uncommon": "罕见",
    "Rare": "稀有",
    "Curse": "诅咒",
    "Status": "状态",
    "Token": "衍生",
    "Event": "事件",
    "Quest": "任务",
    "Ancient": "先古",
}
# Matches localization_zhs/card_keywords.json (display only)
CARD_KW_ZH = {
    "Exhaust": "消耗", "Innate": "固有", "Ethereal": "虚无", "Retain": "保留",
    "Sly": "奇巧", "Eternal": "永恒", "Unplayable": "不能被打出",
}
# End of title line (restrictive / rules)
CARD_KW_SUFFIX_ORDER = ("Exhaust", "Unplayable", "Eternal")
# Before description as [A/B/C]
CARD_KW_PREFIX_ORDER = ("Innate", "Ethereal", "Retain", "Sly")

CARD_TYPE_ZH = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态", "Curse": "诅咒"}
NODE_TYPE_ZH = {"Monster": "怪物", "Elite": "精英", "Boss": "Boss", "RestSite": "休息处",
                "Shop": "商店", "Treasure": "宝箱", "Event": "事件", "Unknown": "未知", "Ancient": "远古",
                "CombatRoom": "战斗", "EliteRoom": "精英", "BossRoom": "Boss",
                "RestSiteRoom": "休息站", "ShopRoom": "商店", "EventRoom": "事件",
                "TreasureRoom": "宝箱", "MapRoom": "地图"}
ROOM_TYPE_ZH = {
    "CombatRoom": "战斗",
    "EventRoom": "事件",
    "RestSiteRoom": "休息站",
    "ShopRoom": "商店",
    "TreasureRoom": "宝箱",
    "BossRoom": "Boss",
    "EliteRoom": "精英",
    "MapRoom": "地图",
}

# ─── Game display ───

SPECIAL_VARS = {
    "energyprefix": "能量" if True else "E",  # placeholder, overridden by LANG
    "energy": "能量",
}

def resolve_template(text, vars_dict):
    """Replace [VarName] in text with actual values from vars dict.
    Matches case-insensitively against the vars dict keys.
    Also handles special vars like energyPrefix."""
    if not text:
        return text
    import re
    # Build case-insensitive lookup from stats + special vars
    lower_vars = {}
    if vars_dict:
        lower_vars = {k.lower(): v for k, v in vars_dict.items()}
    def replacer(m):
        key = m.group(1)
        # Handle plural: [Cards:card|cards]
        if ':' in key and '|' in key:
            var_name, plural_spec = key.split(':', 1)
            val = lower_vars.get(var_name.lower())
            if val is not None:
                forms = plural_spec.split('|')
                return forms[0] if int(val) == 1 else (forms[1] if len(forms) > 1 else forms[0])
            return f"[{key}]"
        kl = key.lower()
        val = lower_vars.get(kl)
        if val is not None:
            return str(val)
        # Special vars
        if kl == "energyprefix":
            return ""  # prefix only, unit already added by energyIcons handler in desc()
        return f"[{key}]"
    return re.sub(r'\[([^\]]+)\]', replacer, text)

def card_desc(card):
    """Get resolved card description using stats as template vars."""
    d = desc(card.get("description", {}))
    stats = card.get("stats") or {}
    return resolve_template(d, stats)  # always resolve (handles energyPrefix etc.)


def _card_kw_label(kw):
    return t(kw, CARD_KW_ZH.get(kw, kw))


def split_card_keywords(keywords):
    """Split into (prefix, suffix) for layout; uses live ``keywords`` from state each call."""
    raw = [k for k in (keywords or []) if k]
    if not raw:
        return [], []
    suffix_set = set(CARD_KW_SUFFIX_ORDER)
    suffix = [k for k in raw if k in suffix_set]
    prefix_rest = [k for k in raw if k not in suffix_set]

    prefix_ordered = []
    used = set()
    for k in CARD_KW_PREFIX_ORDER:
        if k in prefix_rest:
            prefix_ordered.append(k)
            used.add(k)
    for k in prefix_rest:
        if k not in used:
            prefix_ordered.append(k)
            used.add(k)

    suffix_ordered = sorted(suffix, key=lambda k: CARD_KW_SUFFIX_ORDER.index(k))
    return prefix_ordered, suffix_ordered


def format_card_suffix_keywords(suffix_list):
    if not suffix_list:
        return ""
    inner = " ".join(c(_card_kw_label(k), "dim") for k in suffix_list)
    return f" [{inner}]"


def format_card_prefix_tag(prefix_list):
    if not prefix_list:
        return ""
    return "[" + "/".join(_card_kw_label(k) for k in prefix_list) + "]"


def card_description_display_lines(card):
    """Lines under the title row; [前缀词条] merges into first line, then remaining loc lines."""
    cd_d = card_desc(card)
    prefix, _suf = split_card_keywords(card.get("keywords"))
    tag = format_card_prefix_tag(prefix)
    if not cd_d:
        return [tag] if tag else []

    lines = [ln.strip() for ln in cd_d.split("\n") if ln.strip()]
    if not lines:
        return [tag] if tag else []

    if len(lines) == 1:
        return [f"{tag}{lines[0]}" if tag else lines[0]]

    out = []
    if tag:
        out.append(f"{tag}{lines[0]}")
        out.extend(lines[1:])
    else:
        out.extend(lines)
    return out


def combat_hand_inline_stat_str(stats, *, card=None, osty=None):
    """Title-row 伤/挡 from RunSimulator ``stats`` (DynamicVars, keys lowercased).

    Plain ``damage`` is used for Strike-like cards; many attacks use ``calculateddamage``
    or companion hits use ``ostydamage``. Some Necrobinder cards add Osty HP to the card
    total in text but only expose the base in ``stats``—merge using combat ``osty`` blob.
    """
    if not stats:
        stats = {}
    parts = []
    cid = (card or {}).get("id") or ""
    osty_ok = bool(osty and osty.get("alive"))

    dmg = None
    if cid == "CARD.UNLEASH" and osty_ok:
        base = stats.get("calculateddamage")
        if base is None:
            base = stats.get("damage")
        if base is not None:
            hp = osty.get("hp")
            dmg = int(base) + int(hp) if isinstance(hp, (int, float)) else int(base)
    elif cid == "CARD.PROTECTOR" and osty_ok:
        base = stats.get("calculateddamage")
        if base is None:
            base = stats.get("damage")
        if base is not None:
            mhp = osty.get("max_hp")
            dmg = int(base) + int(mhp) if isinstance(mhp, (int, float)) else int(base)

    if dmg is None:
        v = stats.get("damage")
        if v is None:
            v = stats.get("calculateddamage")
        if v is None:
            v = stats.get("ostydamage")
        if v is not None:
            dmg = int(v)

    if dmg is not None:
        parts.append(c(f"{dmg}{t('dmg','伤')}", "red"))
    blk = stats.get("block")
    if blk is not None:
        parts.append(c(f"{blk}{t('blk','挡')}", "blue"))
    return " ".join(parts)


def relic_str(r):
    """Format a relic with name and resolved description."""
    if isinstance(r, dict) and "name" in r:
        name = n(r["name"])
        d = desc(r.get("description", {}))
        # Resolve template vars with actual values
        vars_dict = r.get("vars") or {}
        d = resolve_template(d, vars_dict)
        return f"{name}" + (f": {c(d, 'dim')}" if d else "")
    return n(r)

def potion_str(p):
    """Format a potion with name and resolved description."""
    if isinstance(p, dict) and "name" in p:
        name = n(p["name"])
        d = desc(p.get("description", {}))
        vars_dict = p.get("vars") or {}
        d = resolve_template(d, vars_dict) if vars_dict else d
        idx = p.get("index", "?")
        return f"[{idx}] {name}" + (f": {c(d, 'dim')}" if d else "")
    return n(p)

def show_player(p, show_deck=False):
    hp, mhp = p.get("hp", 0), p.get("max_hp", 1)
    blk = p.get("block", 0)
    gold = p.get("gold", 0)
    deck = p.get("deck_size", 0)
    name = n(p.get("name", "?"))

    print(f"  {c(name, 'bold')}  HP {bar(hp, mhp)} {c(f'{hp}/{mhp}', 'red')}"
          + (f"  {c(str(blk), 'blue')} {t('blk','挡')}" if blk > 0 else "")
          + f"  {t('Gold','金')} {c(str(gold), 'yellow')}  {t('Deck','牌组')} {deck}")
    for r in p.get("relics", []):
        print(f"    🔶 {relic_str(r)}")
    for pot in p.get("potions", []):
        if pot:
            print(f"    🧪 {potion_str(pot)}")
    if show_deck:
        cards = p.get("deck", [])
        if cards:
            print(f"  {c(t('Deck:','牌组:'), 'bold')}")
            for cd in cards:
                up = c("+", "green") if cd.get("upgraded") else ""
                ctype_zh = CARD_TYPE_ZH.get(cd.get("type",""), cd.get("type",""))
                _pre, suf = split_card_keywords(cd.get("keywords"))
                suf_part = format_card_suffix_keywords(suf)
                rare = cd.get("rarity")
                rare_part = f" {c(t(rare, RARITY_ZH.get(rare, rare)), 'dim')}" if rare else ""
                print(f"    {n(cd['name'])}{up} ({cd.get('cost','?')}) {c(t(cd.get('type',''), ctype_zh), 'dim')}{rare_part}{suf_part}")
                print_card_detail_extension(cd, indent="      ")

def show_combat(state):
    rnd = state.get("round", 0)
    energy = state.get("energy", 0)
    max_energy = state.get("max_energy", 0)
    draw = state.get("draw_pile_count", 0)
    discard = state.get("discard_pile_count", 0)

    print(f"\n{'─' * 60}")
    print(f"  {c(t(f'Round {rnd}',f'回合 {rnd}'), 'bold')}  {t('Energy','能量')} {c(f'{energy}/{max_energy}', 'cyan')}  {t('Draw','抽牌')} {draw}  {t('Discard','弃牌')} {discard}")
    show_player(state.get("player", {}))

    # Player powers/buffs/debuffs
    ppowers = state.get("player_powers") or []
    if ppowers:
        for pw in ppowers:
            amt = pw.get("amount", 0)
            amt_str = f" {amt}" if amt and amt != 0 else ""
            pw_desc = desc(pw.get("description", ""))
            if pw_desc and amt:
                pw_desc = resolve_template(pw_desc, {"Amount": abs(amt) if isinstance(amt, (int, float)) else amt})
            is_debuff = isinstance(amt, (int, float)) and amt < 0
            color = "red" if is_debuff else "green"
            label = t("Debuff", "减益") if is_debuff else t("Buff", "增益")
            desc_str = f": {c(pw_desc, 'dim')}" if pw_desc else ""
            pw_name = n(pw.get('name', '?'))
            print(f"    {c(label, color)} {c(f'{pw_name}{amt_str}', color)}{desc_str}")

    # Character-specific: Necrobinder's Osty (show near player)
    osty = state.get("osty")
    if osty:
        if osty.get("alive"):
            ohp, omhp = osty.get("hp", 0), osty.get("max_hp", 1)
            oblk = osty.get("block", 0)
            print(f"    🦴 {n(osty.get('name','Osty'))}  {bar(ohp, omhp)} {ohp}/{omhp}"
                  + (f"  {c(str(oblk), 'blue')}{t('blk','挡')}" if oblk else ""))
        else:
            print(f"    🦴 {c(t('Osty (dead)','Osty (已死亡)'), 'dim')}")

    # Character-specific: Defect's Orbs
    orbs = state.get("orbs")
    if orbs:
        orb_icons = {"Lightning": "⚡", "Frost": "❄", "Dark": "🌑", "Plasma": "🔆", "Glass": "💠"}
        orb_parts = []
        for orb in orbs:
            otype = orb.get("type", "?")
            icon = orb_icons.get(otype, "○")
            pv, ev = orb.get("passive", 0), orb.get("evoke", 0)
            orb_parts.append(f"{icon}{n(orb.get('name', otype))}({pv}/{ev})")
        slots = state.get("orb_slots", len(orbs))
        print(f"    {t('Orbs','充能球')} [{len(orbs)}/{slots}]: {' '.join(orb_parts)}")

    # Character-specific: Regent's Stars
    stars = state.get("stars")
    if stars is not None:
        print(f"    ⭐ {t('Stars','星辰')}: {c(str(stars), 'yellow')}")

    print()
    for e in state.get("enemies", []):
        hp, mhp = e.get("hp", 0), e.get("max_hp", 1)
        blk = e.get("block", 0)

        # Build intent string from detailed intents
        intents = e.get("intents") or []
        intent_parts = []
        for it in intents:
            itype = it.get("type", "")
            dmg = it.get("damage")
            hits = it.get("hits")
            if itype == "Attack":
                if dmg is not None:
                    if hits and hits > 1:
                        intent_parts.append(c(f"⚔{dmg}x{hits}", "red"))
                    else:
                        intent_parts.append(c(f"⚔{dmg}", "red"))
                else:
                    intent_parts.append(c(t("⚔ATK","⚔攻击"), "red"))
            elif itype == "Defend":
                intent_parts.append(c(t("🛡DEF","🛡防御"), "blue"))
            elif itype in ("Buff", "Heal"):
                intent_parts.append(c(t(f"⬆{itype}",f"⬆{'增益' if itype=='Buff' else '回复'}"), "magenta"))
            elif itype == "Debuff":
                intent_parts.append(c(t("⬇Debuff","⬇减益"), "yellow"))
            elif itype == "DebuffStrong":
                intent_parts.append(c(t("⬇Strong","⬇强减益"), "yellow"))
            elif itype in ("CardDebuff", "StatusCard"):
                intent_parts.append(c(t("⬇Cards","⬇塞牌"), "yellow"))
            elif itype == "DeathBlow":
                if dmg is not None:
                    intent_parts.append(c(f"💀{dmg}", "red"))
                else:
                    intent_parts.append(c(t("💀KILL","💀致命一击"), "red"))
            elif itype == "Escape":
                intent_parts.append(c(t("🏃Escape","🏃逃跑"), "dim"))
            elif itype == "Summon":
                intent_parts.append(c(t("📢Summon","📢召唤"), "magenta"))
            elif itype == "Sleep":
                intent_parts.append(c(t("💤Sleep","💤休眠"), "dim"))
            elif itype == "Stun":
                intent_parts.append(c(t("⚡Stun","⚡眩晕"), "yellow"))
            elif itype == "Hidden":
                intent_parts.append(c("? ???", "dim"))
            elif itype:
                intent_parts.append(c(itype, "dim"))
        intent_str = " ".join(intent_parts) if intent_parts else c("? ???", "dim")

        # Enemy powers
        powers = e.get("powers") or []
        power_str = ""
        if powers:
            pw_parts = [f"{n(pw['name'])} {pw.get('amount','')}" for pw in powers]
            power_str = "  " + c(", ".join(pw_parts), "dim")

        print(f"  [{e['index']}] {n(e['name'])}  {bar(hp, mhp)} {hp}/{mhp}"
              + (f"  {c(str(blk), 'blue')} {t('blk','挡')}" if blk else "")
              + f"  {intent_str}{power_str}")

    print()
    hand = state.get("hand", [])
    for card in hand:
        cost = card.get("cost", 0)
        playable = card.get("can_play", False)
        ctype = card.get("type", "?")
        target = card.get("target_type", "")

        type_color = {"Attack": "red", "Skill": "blue", "Power": "magenta", "Status": "dim", "Curse": "dim"}.get(ctype, "reset")
        mark = c("●", "green") if playable else c("○", "dim")
        star_cost = card.get("star_cost", 0)
        cost_str = c(str(cost), "cyan")
        if star_cost > 0:
            cost_str += f"+{c(f'{star_cost}⭐', 'yellow')}"

        # Damage/block inline on title row; suffix keywords (e.g. 消耗) at end of title row
        stat_str = combat_hand_inline_stat_str(
            card.get("stats") or {}, card=card, osty=state.get("osty")
        )

        _pre, suf = split_card_keywords(card.get("keywords"))
        suf_part = format_card_suffix_keywords(suf)
        ench = card.get("enchantment")
        ench_str = f" {c(n(ench), 'magenta')}" if ench else ""

        print(f"  {mark} [{card['index']}] {c(n(card['name']), type_color)}{ench_str} ({cost_str}) {stat_str}{suf_part}"
              + (f"  {c('→','yellow')}" if target == "AnyEnemy" else ""))

        print_card_detail_extension(card, indent="      ")

def show_map(state, send_fn=None):
    """Show map at map_select. Fetches full map if send_fn available."""
    choices = state.get("choices", [])
    choice_set = {(ch["col"], ch["row"]) for ch in choices}

    # Try to fetch full map for richer display
    if send_fn:
        map_data = send_fn({"cmd": "get_map"})
        if map_data and map_data.get("type") == "map":
            # Build index map: (col,row) → choice index
            choice_indices = {(ch["col"], ch["row"]): i for i, ch in enumerate(choices)}
            _render_map(map_data, choice_set, choice_indices)
            return

    # Fallback: simple list
    ctx = state.get("context", {})
    act_name = n(ctx.get("act_name", "?"))
    floor = ctx.get("floor", "?")
    print(f"\n{'═' * 60}")
    print(f"  {c(f'{act_name}', 'bold')} {t('Floor','层')} {floor}")
    show_player(state.get("player", {}))
    print()
    type_icons = {
        "Monster": "⚔", "Elite": "💀", "Boss": "👹",
        "RestSite": "🏕", "Shop": "🏪", "Treasure": "💎",
        "Event": "❓", "Unknown": "❓", "Ancient": "🏛",
    }
    for i, ch in enumerate(choices):
        icon = type_icons.get(ch["type"], "?")
        ntype = t(ch["type"], NODE_TYPE_ZH.get(ch["type"], ch["type"]))
        print(f"  [{i}] {icon} {ntype}")

def _format_upgrade_preview(stats, aug, current_cost=None):
    """Format upgrade preview string."""
    if not aug:
        return None
    aug_stats = aug.get("stats") or {}
    parts = []
    # Cost change
    aug_cost = aug.get("cost")
    if current_cost is not None and aug_cost is not None and aug_cost != current_cost:
        parts.append(c(f"{t('cost','费用')} {current_cost}→{aug_cost}", "green"))
    # Compare all stats, show changed values with readable names
    all_keys = set(list(stats.keys()) + list(aug_stats.keys()))
    for k in sorted(all_keys):
        old = stats.get(k, 0)
        new_val = aug_stats.get(k, old)
        if new_val != old:
            if k == "damage":
                parts.append(c(f"{t('dmg','伤害')} {old}→{new_val}", "red"))
            elif k == "block":
                parts.append(c(f"{t('blk','格挡')} {old}→{new_val}", "blue"))
            else:
                parts.append(c(f"{old}→{new_val}", "green"))
    # Keyword changes (e.g., Discovery removes Exhaust)
    for kw in (aug.get("removed_keywords") or []):
        parts.append(c(f"-{_card_kw_label(kw)}", "green"))
    for kw in (aug.get("added_keywords") or []):
        parts.append(c(f"+{_card_kw_label(kw)}", "yellow"))
    return parts


def print_card_detail_extension(card, indent="      "):
    """Description (with [prefix/keywords]) + upgrade preview; indent matches title row spacing."""
    for line in card_description_display_lines(card):
        if line:
            print(f"{indent}{c(line, 'dim')}")
    stats = card.get("stats") or {}
    aug_parts = _format_upgrade_preview(stats, card.get("after_upgrade"), card.get("cost"))
    if aug_parts:
        print(f"{indent}{c(t('upgrade:','升级:'), 'green')} {', '.join(aug_parts)}")


def card_pick_quantity_hint(mn, mx):
    """Short hint for prompts / help (N–M cards)."""
    if mn == mx:
        if mn == 1:
            return t("pick 1 card", "选 1 张")
        return t(f"pick exactly {mn} cards", f"须选 {mn} 张")
    if mn == 0:
        return t(f"pick 0–{mx} cards (or s to skip)", f"可选 0–{mx} 张（或 s 跳过）")
    return t(f"pick {mn}–{mx} cards", f"须选 {mn}–{mx} 张")


def show_card_reward(state):
    print(f"\n{'─' * 60}")
    gold_earned = state.get("gold_earned", 0)
    if gold_earned > 0:
        print(f"  {c(t('Combat won!','战斗胜利!'), 'green')} +{c(str(gold_earned), 'yellow')}{t('g','金')}")
    print(f"  {c(t('Card Reward','卡牌奖励'), 'bold')} — {t('choose one (or skip)','选一张（或跳过）')}")
    show_player(state.get("player", {}))
    print()
    cards = state.get("cards", [])
    for card in cards:
        ctype = card.get("type", "?")
        rarity = card.get("rarity", "Common")
        cost = card.get("cost", "?")
        type_color = {"Attack": "red", "Skill": "blue", "Power": "magenta"}.get(ctype, "reset")
        rarity_zh = RARITY_ZH.get(rarity, rarity)
        rarity_label = t(rarity, rarity_zh)
        rarity_color = {"Rare": "yellow", "Uncommon": "cyan"}.get(rarity, "dim")
        _pre, suf = split_card_keywords(card.get("keywords"))
        suf_part = format_card_suffix_keywords(suf)
        print(f"  [{card['index']}] {c(n(card['name']), type_color)} ({cost}) {c(rarity_label, rarity_color)}{suf_part}")
        print_card_detail_extension(card, indent="      ")

    print()
    if cards:
        hi = len(cards) - 1
        print(f"  {c(t(f'Pick one card: type index 0–{hi}, or s to skip.', f'请选择一张：输入编号 0–{hi}，或 s 跳过。'), 'yellow')}")
    else:
        print(f"  {c(t('No cards to pick.', '没有可选卡牌。'), 'dim')}")

def show_shop(state):
    print(f"\n{'─' * 60}")
    print(f"  {c(t('Shop','商店'), 'bold')}")
    show_player(state.get("player", {}))
    gold = state.get("player", {}).get("gold", 0)

    print(f"\n  {c(t('Cards:','卡牌:'), 'bold')}")
    for card in state.get("cards", []):
        if not card.get("is_stocked"): continue
        cost = card.get("cost", 0)
        affordable = c(str(cost), "green") if cost <= gold else c(str(cost), "red")
        sale = c(t(" SALE"," 打折"), "yellow") if card.get("on_sale") else ""
        ctype_zh = CARD_TYPE_ZH.get(card.get("type",""), card.get("type",""))
        cc = card.get("card_cost", "?")
        _pre, suf = split_card_keywords(card.get("keywords"))
        suf_part = format_card_suffix_keywords(suf)
        print(f"  [{card['index']}] {n(card['name'])} ({cc}) {c(t(card.get('type','?'), ctype_zh), 'dim')}{suf_part} — {affordable}{t('g','金')}{sale}")
        print_card_detail_extension(card, indent="      ")

    print(f"\n  {c(t('Relics:','遗物:'), 'bold')}")
    for r in state.get("relics", []):
        if not r.get("is_stocked"): continue
        cost = r.get("cost", 0)
        affordable = c(str(cost), "green") if cost <= gold else c(str(cost), "red")
        r_desc = desc(r.get("description", ""))
        print(f"  [r{r['index']}] {n(r['name'])} — {affordable}{t('g','金')}")
        if r_desc:
            print(f"      {c(r_desc, 'dim')}")

    print(f"\n  {c(t('Potions:','药水:'), 'bold')}")
    for p in state.get("potions", []):
        if not p.get("is_stocked"): continue
        cost = p.get("cost", 0)
        affordable = c(str(cost), "green") if cost <= gold else c(str(cost), "red")
        p_desc = desc(p.get("description", ""))
        print(f"  [p{p['index']}] {n(p['name'])} — {affordable}{t('g','金')}")
        if p_desc:
            print(f"      {c(p_desc, 'dim')}")

    removal_cost = state.get("card_removal_cost")
    if removal_cost:
        affordable = c(str(removal_cost), "green") if removal_cost <= gold else c(str(removal_cost), "red")
        print(f"\n  [rm] {t('Remove a card','移除一张牌')} — {affordable}{t('g','金')}")

    print(f"\n  [leave] {t('Leave shop','离开商店')}")

REST_OPTIONS_ZH = {"HEAL": "休息", "SMITH": "升级", "LIFT": "锻炼", "DIG": "挖掘", "RECALL": "回忆", "TOKE": "吸食"}

def show_rest_site(state):
    print(f"\n{'─' * 60}")
    ctx = state.get("context", {})
    if ctx:
        print(f"  {c(n(ctx.get('act_name','?')), 'dim')} {t('Floor','层')} {ctx.get('floor','?')}")
    print(f"  {c(t('Rest Site','休息处'), 'bold')}")
    show_player(state.get("player", {}))
    print()
    for opt in state.get("options", []):
        enabled = opt.get("is_enabled", True)
        mark = c("●", "green") if enabled else c("○", "dim")
        opt_id = opt.get("option_id", "?")
        opt_name = t(opt_id, REST_OPTIONS_ZH.get(opt_id, opt_id))
        opt_desc = opt.get("name", "")
        print(f"  {mark} [{opt['index']}] {opt_name}" + (f" — {opt_desc}" if opt_desc and opt_desc != opt_id else ""))

def _load_loc():
    """Load localization data for resolving event option names."""
    if not hasattr(_load_loc, '_cache'):
        _load_loc._cache = {}
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for lang in ['localization_eng', 'localization_zhs']:
            d = os.path.join(base, lang)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith('.json'):
                        try:
                            data = json.load(open(os.path.join(d, f)))
                            table = f[:-5]
                            if table not in _load_loc._cache:
                                _load_loc._cache[table] = {}
                            for k, v in data.items():
                                key = f"{table}:{k}"
                                if key not in _load_loc._cache:
                                    _load_loc._cache[key] = v
                                elif lang == 'localization_zhs':
                                    _load_loc._cache[key + ':zh'] = v
                        except Exception:
                            pass
    return _load_loc._cache

def loc_resolve(key):
    """Resolve a loc key like 'NEOW.pages.INITIAL.options.PRECISE_SCISSORS.title' to readable text."""
    cache = _load_loc()
    # Try direct lookup in relevant tables
    for table in ['events', 'relics', 'ancients', 'cards', 'potions', 'monsters']:
        val_en = cache.get(f"{table}:{key}")
        val_zh = cache.get(f"{table}:{key}:zh")
        if val_en:
            return n({"en": val_en, "zh": val_zh}) if val_zh else val_en
    # Extract meaningful part from key
    parts = key.split('.')
    for p in reversed(parts):
        if p not in ('title', 'description', 'options', 'pages', 'INITIAL'):
            relic_en = cache.get(f"relics:{p}.title")
            relic_zh = cache.get(f"relics:{p}.title:zh")
            desc_en = cache.get(f"relics:{p}.description", "")
            desc_zh = cache.get(f"relics:{p}.description:zh", "")
            if relic_en:
                name = n({"en": relic_en, "zh": relic_zh})
                d = desc({"en": desc_en, "zh": desc_zh})
                return f"{name}" + (f" — {c(d, 'dim')}" if d else "")
            return p.replace('_', ' ').title()
    return key

def show_event(state):
    print(f"\n{'─' * 60}")
    event_name = state.get("event_name", "?")
    # event_name is now bilingual dict {"en": ..., "zh": ...} or plain string
    event_display = n(event_name) if isinstance(event_name, dict) else event_name
    event_desc = state.get("description", "")
    # Show context
    ctx = state.get("context", {})
    if ctx:
        act = n(ctx.get("act_name", "?"))
        floor = ctx.get("floor", "?")
        print(f"  {c(act, 'dim')} {t('Floor','层')} {floor}")
    event_label = t("Event", "事件")
    print(f"  {c(f'{event_label}: {event_display}', 'bold')}")
    # event_desc is usually a raw loc key — skip it (event name already in title)
    show_player(state.get("player", {}))
    print()
    for opt in state.get("options", []):
        locked = opt.get("is_locked", False)
        mark = c("○", "dim") if locked else c("●", "green")
        raw_title = opt.get("title", opt.get("text_key", f"Option {opt['index']}"))
        # title is now bilingual dict or loc key string
        if isinstance(raw_title, dict):
            title = n(raw_title)
        else:
            title = loc_resolve(raw_title) if '.' in str(raw_title) or str(raw_title).isupper() else raw_title
        # Show option description with resolved template vars
        raw_desc = opt.get("description")
        opt_desc = desc(raw_desc) if raw_desc else ""
        # Resolve template vars like [MaxHp], [Gold], {Cards}
        opt_vars = opt.get("vars") or {}
        if opt_vars and opt_desc:
            opt_desc = resolve_template(opt_desc, opt_vars)
        desc_str = f" — {c(opt_desc, 'dim')}" if opt_desc else ""
        print(f"  {mark} [{opt['index']}] {title}{desc_str}")

# ─── Input handling ───

def _render_map(map_data, choice_set=None, choice_indices=None):
    """Render map as a grid with connection lines between rows."""
    if choice_set is None:
        choice_set = set()
    if choice_indices is None:
        choice_indices = {}

    ctx = map_data.get("context", {})
    act = n(ctx.get("act_name", "?"))
    floor_n = ctx.get("floor", "?")
    cur = map_data.get("current_coord")

    ICONS = {
        "Monster": "M", "Elite": "E", "Boss": "B",
        "RestSite": "R", "Shop": "$", "Treasure": "T",
        "Event": "?", "Unknown": "?", "Ancient": "A",
    }

    rows = map_data.get("rows", [])
    if not rows:
        return

    # Collect nodes and edges
    node_map = {}
    max_col = 0
    row_numbers = set()
    # edges_up[lower_row] = [(from_col, to_col), ...] where to is in the row above
    edges_up = {}
    for row in rows:
        for nd in row:
            col, rn = nd.get("col", 0), nd.get("row", 0)
            node_map[(col, rn)] = nd
            max_col = max(max_col, col)
            row_numbers.add(rn)
            for ch in (nd.get("children") or []):
                edges_up.setdefault(rn, []).append((col, ch["col"]))

    row_numbers = sorted(row_numbers)
    total_cols = max_col + 1
    W = 4  # chars per column cell
    # Center of column c = c*W + W//2 = c*4 + 2

    width = W * total_cols + 6
    print(f"\n{'═' * width}")
    print(f"  {c(act, 'bold')} — {t('Floor','层')} {floor_n}")
    # Show current position if it's not on the map grid (e.g., starting row 0)
    if cur and cur.get("row", -1) not in row_numbers:
        print(f"  {c(t('You are at the start','你在起点'), 'green')}")
    print()

    # Boss row
    boss = map_data.get("boss", {})
    boss_col = boss.get("col", 0)
    boss_row = boss.get("row", -1)
    buf = list(" " * (W * total_cols))
    buf[boss_col * W + W // 2] = "B"
    line = "".join(buf)
    line = line[:boss_col * W + W // 2] + c("B", "red") + line[boss_col * W + W // 2 + 1:]
    print(f"  {c('B','dim')} | {line}")

    # Connection from top row to boss
    top_rn = row_numbers[-1] if row_numbers else -1
    conn = list(" " * (W * total_cols))
    for fc, tc in edges_up.get(top_rn, []):
        if tc == boss_col:  # this edge's target row should be boss
            pass
    # Actually, edges_up[top_rn] has edges from top_rn to its children.
    # Children of top row nodes go to boss.
    for nd_row in rows:
        for nd in nd_row:
            if nd.get("row") == top_rn:
                for ch in (nd.get("children") or []):
                    if ch.get("row") == boss_row:
                        fc, tc = nd["col"], ch["col"]
                        _draw_conn(conn, fc, tc, W)
    print(f"    | {c(''.join(conn), 'dim')}")

    # Map rows (top to bottom)
    for idx in range(len(row_numbers) - 1, -1, -1):
        rn = row_numbers[idx]

        # --- Node line ---
        buf = list(" " * (W * total_cols))
        color_subs = []  # (start_pos, end_pos, colored_str)
        for col in range(total_cols):
            nd = node_map.get((col, rn))
            if not nd:
                continue
            icon = ICONS.get(nd.get("type", "?"), "·")
            is_cur = (cur and cur["col"] == col and cur["row"] == rn)
            is_choice = (col, rn) in choice_set
            visited = nd.get("visited", False)

            center = col * W + W // 2
            choice_idx = choice_indices.get((col, rn))
            if is_cur:
                buf[center - 1] = "["
                buf[center] = icon
                buf[center + 1] = "]"
                color_subs.append((center - 1, center + 2, c(f"[{icon}]", "green")))
            elif choice_idx is not None:
                buf[center] = icon
                color_subs.append((center, center + 1, c(icon, "yellow")))
            elif visited:
                buf[center] = icon
                color_subs.append((center, center + 1, c(icon, "dim")))
            else:
                buf[center] = icon

        line = "".join(buf)
        # Apply colors right-to-left
        for start, end, colored in sorted(color_subs, key=lambda x: -x[0]):
            line = line[:start] + colored + line[end:]
        print(f"  {rn:>2}| {line}")

        # --- Choice index annotation line ---
        row_choices = {col: choice_indices[(col, rn)] for col in range(total_cols) if (col, rn) in choice_indices}
        if row_choices:
            ann = list(" " * (W * total_cols))
            ann_subs = []
            for col, idx in row_choices.items():
                label = f"[{idx}]"
                start = col * W + W // 2 - 1
                for j, ch in enumerate(label):
                    if 0 <= start + j < len(ann):
                        ann[start + j] = ch
                ann_subs.append((start, start + len(label), c(label, "yellow")))
            ann_line = "".join(ann)
            for start, end, colored in sorted(ann_subs, key=lambda x: -x[0]):
                ann_line = ann_line[:start] + colored + ann_line[end:]
            print(f"    | {ann_line}")

        # --- Connection line below this row (edges from row below going up to this row) ---
        if idx > 0:
            below_rn = row_numbers[idx - 1]
            conn = list(" " * (W * total_cols))
            for fc, tc in edges_up.get(below_rn, []):
                # fc is in below_rn, tc is the child row
                # We need edges where child row == rn
                pass
            # Rebuild: iterate edges from below_rn whose children are in rn
            for nd_row in rows:
                for nd in nd_row:
                    if nd.get("row") != below_rn:
                        continue
                    for ch in (nd.get("children") or []):
                        if ch.get("row") == rn:
                            _draw_conn(conn, nd["col"], ch["col"], W)
            print(f"    | {c(''.join(conn), 'dim')}")

    # Legend
    print(f"  {'─' * width}")
    legend = (f"  M={t('Monster','怪物')} E={t('Elite','精英')} R={t('Rest','休息')} "
              f"$={t('Shop','商店')} T={t('Treasure','宝箱')} ?={t('Event','事件')} "
              f"{c('[x]','green')}={t('You','当前')} {c('0','yellow')}={t('Choice','可选')}")
    print(legend)
    # Show choice details
    if choice_indices:
        inv = {v: k for k, v in choice_indices.items()}
        parts = []
        for i in sorted(inv.keys()):
            col, row = inv[i]
            nd = node_map.get((col, row))
            if nd:
                ntype = t(nd.get("type", "?"), NODE_TYPE_ZH.get(nd.get("type", ""), nd.get("type", "?")))
                parts.append(f"{c(str(i), 'yellow')}={ntype}")
        print(f"  {' '.join(parts)}")
    print()


def _draw_conn(buf, from_col, to_col, W):
    """Draw a connection between two columns on one line.
    from_col = lower row node, to_col = upper row node.
    Single char at midpoint: | for straight, / for up-right, \\ for up-left."""
    fc = from_col * W + W // 2
    tc = to_col * W + W // 2
    if from_col == to_col:
        if 0 <= fc < len(buf):
            buf[fc] = "|"
    else:
        mid = (fc + tc) // 2
        ch = "/" if from_col < to_col else "\\"
        if 0 <= mid < len(buf):
            buf[mid] = ch

def get_input(prompt, valid_options=None, state=None, multi_select=False, multi_min=1, multi_max=1):
    """Get user input with validation. Supports meta-commands: help, map, deck, potions.

    If multi_select is True, accept comma-separated tokens; each must be in valid_options,
    and the count must be between multi_min and multi_max (inclusive).
    """
    while True:
        try:
            raw = input(f"\n{c('>', 'green')} {prompt}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise _QuitRequested()

        if not raw:
            continue

        # Meta-commands available at any prompt
        if raw == "help":
            if LANG == "zh":
                print(f"""
  {c('命令:', 'bold')}
    {c('help', 'cyan')}     — 帮助
    {c('map', 'cyan')}      — 显示地图
    {c('deck', 'cyan')}     — 查看牌组
    {c('potions', 'cyan')}  — 查看药水
    {c('relics', 'cyan')}   — 查看遗物
    {c('quit', 'cyan')}     — 退出
    {c('save', 'cyan')}     — 存档
    {c('saves', 'cyan')}    — 查看存档列表

  {c('操作:', 'bold')}
    地图:    输入路径编号 (0, 1, 2)
    战斗:    卡牌编号 / {c('e', 'yellow')} 结束回合 / {c('p0', 'yellow')} 使用药水
    奖励:    卡牌编号 / {c('s', 'yellow')} 跳过
    多选:    按提示选择张数（须选 N–M 张 / 可选 0–M 张等），编号逗号分隔，例如 {c('0,1,2', 'yellow')}
    休息:    选项编号
    事件:    选项编号 / {c('leave', 'yellow')} 离开
    商店:    {c('c0', 'yellow')} 买卡 / {c('r0', 'yellow')} 遗物 / {c('p0', 'yellow')} 药水 / {c('rm', 'yellow')} 移除 / {c('leave', 'yellow')} 离开
""")
            else:
                print(f"""
  {c('Commands:', 'bold')}
    {c('help', 'cyan')}     — show this help
    {c('map', 'cyan')}      — show map
    {c('deck', 'cyan')}     — show deck
    {c('potions', 'cyan')}  — show potions
    {c('relics', 'cyan')}   — show relics
    {c('quit', 'cyan')}     — quit
    {c('abandon', 'cyan')}  — abandon run (forfeit)
    {c('save', 'cyan')}     — save game
    {c('saves', 'cyan')}    — list saves

  {c('Actions:', 'bold')}
    Map:     path number (0, 1, 2)
    Combat:  card index / {c('e', 'yellow')} end turn / {c('p0', 'yellow')} use potion
    Reward:  card index / {c('s', 'yellow')} skip
    Multi:   when prompted for N–M cards (or 0–M optional), comma-separate indices, e.g. {c('0,1,2', 'yellow')}
    Rest:    option index
    Event:   option index / {c('leave', 'yellow')} leave
    Shop:    {c('c0', 'yellow')} card / {c('r0', 'yellow')} relic / {c('p0', 'yellow')} potion / {c('rm', 'yellow')} remove / {c('leave', 'yellow')} leave
""")
            continue
        if raw == "deck" and state:
            p = state.get("player", {})
            show_player(p, show_deck=True)
            continue
        if raw == "potions" and state:
            p = state.get("player", {})
            pots = p.get("potions", [])
            if pots:
                for pot in pots:
                    if pot: print(f"  🧪 {potion_str(pot)}")
            else:
                print(f"  {t('No potions.','没有药水。')}")
            continue
        if raw == "relics" and state:
            p = state.get("player", {})
            for r in p.get("relics", []):
                print(f"  🔶 {relic_str(r)}")
            continue
        if raw == "map":
            # Fetch full map from CLI
            if hasattr(get_input, '_send'):
                map_data = get_input._send({"cmd": "get_map"})
                if map_data and map_data.get("type") == "map":
                    _render_map(map_data)
                else:
                    print("  Map not available.")
            elif state:
                ctx = state.get("context", {})
                print(f"  {c(n(ctx.get('act_name','?')), 'bold')} {t('Floor','层')} {ctx.get('floor','?')}")
            continue
        if raw == "save":
            if hasattr(get_input, '_save_fn'):
                get_input._save_fn()
            else:
                print(f"  {t('Save not available.','存档不可用。')}")
            continue
        if raw == "saves":
            saves = _list_saves()
            if saves:
                print(f"\n  {c(t('Saved games:','存档列表:'), 'bold')}")
                for s in saves:
                    print(f"    {c(s['file'], 'cyan')}  {s['character']}  {t('Seed','种子')}:{s['seed']}  {t('Actions','操作数')}:{s['actions']}")
                print(f"\n  {t('Load with:','读档命令:')} python3 play.py --load saves/{saves[0]['file']}")
            else:
                print(f"  {t('No saves found.','没有找到存档。')}")
            continue
        if raw == "quit":
            raise _QuitRequested()
        if raw == "abandon":
            confirm = input(f"  {t('Abandon this run? (y/n): ','放弃本次运行？(y/n): ')}")
            if confirm.strip().lower() in ("y", "yes", "是"):
                raise KeyboardInterrupt("abandon")
            continue

        if valid_options:
            if multi_select and multi_max > 1:
                if multi_min == 0 and raw == "s" and "s" in valid_options:
                    return raw
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                if not parts:
                    print(f"  {t('Invalid. Options:','无效。选项:')} {', '.join(sorted(valid_options))}")
                    continue
                if len(parts) < multi_min or len(parts) > multi_max:
                    q = card_pick_quantity_hint(multi_min, multi_max)
                    print(f"  {q} — {t(f'Use {multi_min}-{multi_max} comma-separated indices (e.g. 0,1).', f'逗号分隔输入 {multi_min}–{multi_max} 个编号（例 0,1）。')}")
                    continue
                if len(parts) != len(set(parts)):
                    print(f"  {t('Duplicate indices.','编号重复。')}")
                    continue
                bad = [p for p in parts if p not in valid_options]
                if bad:
                    print(f"  {t('Invalid. Options:','无效。选项:')} {', '.join(sorted(valid_options))}")
                    continue
                return ",".join(parts)
            if raw not in valid_options:
                print(f"  {t('Invalid. Options:','无效。选项:')} {', '.join(sorted(valid_options))}")
                continue
        return raw

# ─── Main game loop ───

def _save_game(save_path, character, seed, action_log):
    """Write action replay save file."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    data = {"character": character, "seed": seed, "actions": action_log}
    with open(save_path, "w") as f:
        json.dump(data, f, indent=2)

def _load_game(save_path):
    """Read action replay save file. Returns (character, seed, actions)."""
    try:
        with open(save_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{t('Error:','错误:')} Save file is not valid JSON: {save_path}")
        print(f"  {e}")
        sys.exit(1)
    if "actions" not in data:
        print(f"{t('Error:','错误:')} Not a replay save file (missing 'actions' key): {save_path}")
        sys.exit(1)
    return data["character"], data["seed"], data["actions"]

def _list_saves():
    """List available save files (replay .json and native .save files)."""
    if not os.path.isdir(SAVE_DIR):
        return []
    saves = []
    for f in sorted(os.listdir(SAVE_DIR)):
        path = os.path.join(SAVE_DIR, f)
        if f.endswith(".json"):
            # Only list .json files that are replay saves (have "actions" key)
            try:
                with open(path) as fh:
                    d = json.load(fh)
                if "actions" not in d:
                    continue  # skip non-replay JSON files
                saves.append({
                    "file": f, "path": path, "type": "replay",
                    "character": d.get("character", "?"),
                    "seed": d.get("seed", "?"),
                    "actions": len(d.get("actions", [])),
                })
            except Exception:
                pass
        elif f.endswith(".save"):
            # Native save files
            saves.append({
                "file": f, "path": path, "type": "native",
                "character": "?", "seed": "?", "actions": "—",
            })
    return saves

class _QuitRequested(Exception):
    pass

def _quit_with_save(native_save_path, character, seed):
    """Return the save path to use on quit, or None to quit without saving."""
    print()
    try:
        ans = input(f"  {t('Save before quitting? (y/n): ','退出前是否存档？(y/n): ')}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans not in ("y", "yes", "是"):
        print(f"  {t('Quitting without saving.','退出，未保存。')}")
        return None

    if native_save_path:
        return native_save_path

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    char_tag = (character or "run").lower()
    seed_tag = seed or "random"
    return os.path.join(SAVE_DIR, f"{char_tag}_{seed_tag}_{ts}.save")


def _show_quit_save_result(result):
    """Print save confirmation or failure from a quit_result response."""
    save_result = result.get("save") if result else None
    if save_result and save_result.get("success"):
        sz = save_result.get("size", 0)
        save_path = save_result.get("path")
        print(f"  {c(t('Saved!','已存档!'), 'green')} ({sz // 1024}KB)")
        if save_path:
            print(f"  {t('Save path:','存档位置:')} {c(save_path, 'cyan')}")
            print(f"  {t('Continue later:','下次继续:')} python3 play.py --continue {save_path}")
    elif save_result:
        print(f"  {c(t('Save failed:','存档失败:'), 'red')} {save_result.get('message', '?')}")


def _writeback_continue_save(send_fn, native_save_path):
    """Best-effort writeback for --continue sessions when a stable map checkpoint is reached."""
    if not native_save_path:
        return
    result = send_fn({"cmd": "write_continue_save", "path": native_save_path})
    if result and result.get("success"):
        sz = result.get("size", 0)
        print(f"  {c(t(f'Save written ({sz//1024}KB)', f'存档已写入 ({sz//1024}KB)'), 'dim')}")
    elif result:
        print(f"  {c(t('Save failed:','存档写入失败:'), 'red')} {result.get('message','?')}")


def play(character="Ironclad", seed=None, auto=False, ascension=0, log=True,
         load_path=None, native_save_path=None):
    actual_seed = seed or f"cli_{random.randint(1000,9999)}"
    replay_actions = None
    restart_requested = False
    quit_sent = False

    if load_path:
        character, actual_seed, replay_actions = _load_game(load_path)
        print(f"\n{c(t('Loading save...','读取存档...'), 'yellow')} {os.path.basename(load_path)}")
        print(f"  {t('Character','角色')}: {character}  {t('Seed','种子')}: {actual_seed}  {t('Actions','操作数')}: {len(replay_actions)}")

    logger = GameLogger(character, actual_seed, enabled=log)
    action_log = []
    proc = subprocess.Popen(
        [DOTNET, "run", "--no-build", "--project", PROJECT],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )

    def read():
        while True:
            l = proc.stdout.readline().strip()
            if not l:
                return None
            if l.startswith("{"):
                resp = json.loads(l)
                logger.log_state(resp)
                return resp

    def send(cmd, record=True):
        logger.log_action(cmd)
        if record and cmd.get("cmd") == "action":
            action_log.append(cmd)
        proc.stdin.write(json.dumps(cmd) + "\n")
        proc.stdin.flush()
        return read()

    # Wire send into get_input for map command
    get_input._send = send

    def do_save():
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{character}_{actual_seed}_{ts}.json"
        save_path = os.path.join(SAVE_DIR, fname)
        _save_game(save_path, character, actual_seed, action_log)
        print(f"  {c(t('Saved!','已存档!'), 'green')} {fname} ({len(action_log)} {t('actions','步操作')})")
        print(f"  {t('Load with:','读档命令:')} python3 play.py --load {os.path.relpath(save_path, ROOT)}")

    get_input._save_fn = do_save
    try:
        ready = read()
        if not ready:
            print("Failed to start simulator")
            return

        game_lang = "en" if LANG == "en" else "zh"
        if native_save_path:
            print(f"  {t('Loading game save...','加载游戏存档...')}")
            state = send(
                {"cmd": "load_save", "path": native_save_path, "lang": game_lang},
                record=False,
            )
            if state and state.get("type") == "error":
                print(f"  {c(t('Error:','错误:'), 'red')} {state.get('message', '?')}")
                return
            p = state.get("player", {}) if state else {}
            char_name = p.get("name", {})
            if isinstance(char_name, dict):
                character = char_name.get("en", character)
            print(f"  {c(t('Save loaded!','存档加载成功!'), 'green')}")
        else:
            # Map display lang to game engine lang: "both" falls back to "zh".
            state = send({
                "cmd": "start_run",
                "character": character,
                "seed": actual_seed,
                "ascension": ascension,
                "lang": game_lang,
            }, record=False)
            if state and state.get("type") == "error":
                print(f"  {c(t('Error:','错误:'), 'red')} {state.get('message', '?')}")
                return

            # Replay saved actions silently
            if replay_actions:
                total = len(replay_actions)
                for i, cmd in enumerate(replay_actions):
                    state = send(cmd, record=True)
                    pct = (i + 1) * 100 // total
                    print(f"\r  {t('Replaying','回放中')}... {pct}% ({i+1}/{total})", end="", flush=True)
                    if not state:
                        print(f"\n{c(t('Replay failed at action','回放失败于操作'), 'red')} {i+1}")
                        return
                print(f"\r  {c(t('Replay complete!','回放完成!'), 'green')}" + " " * 30)
                print()
        print(f"\n{c(t('Slay the Spire 2 — Headless CLI', '杀戮尖塔 2 — 终端版'), 'bold')}")
        if native_save_path:
            p = state.get("player", {}) if state else {}
            ctx = state.get("context", {}) if state else {}
            print(f"{t('Character','角色')}: {n(p.get('name','?'))}  "
                  f"{t('Act','幕')}: {ctx.get('act','?')} ({n(ctx.get('act_name','?'))})  "
                  f"{t('HP','生命')}: {p.get('hp','?')}/{p.get('max_hp','?')}  "
                  f"{t('Gold','金')}: {p.get('gold','?')}")
        else:
            asc_str = f"  {t('Ascension','渐进难度')}: {ascension}" if ascension > 0 else ""
            print(f"{t('Character','角色')}: {character}  {t('Seed','种子')}: {actual_seed}{asc_str}")
        print(f"{t('Type','输入')} {c('help', 'cyan')} {t('for available commands.','查看可用命令。')}\n")

        _auto_last_fingerprint = None
        _auto_stuck_count = 0

        while True:
            if not state:
                print(t("Connection lost.","连接已断开。"))
                break

            if state.get("type") == "error":
                print(f"  {c(t('Error:','错误:'), 'red')} {state.get('message', '?')}")
                state = send({"cmd": "action", "action": "proceed"})
                continue

            dec = state.get("decision", "")

            if dec == "game_over":
                victory = state.get("victory", False)
                p = state.get("player", {})
                ctx = state.get("context", {})

                print(f"\n{'═' * 60}")
                if victory:
                    print(f"  {c('★ ★ ★', 'yellow')}  {c(t('VICTORY!','胜利!'), 'green')}  {c('★ ★ ★', 'yellow')}")
                else:
                    print(f"  {c(t('DEFEAT','战败'), 'red')}")
                print()

                act_name = n(ctx.get("act_name", "?"))
                floor = state.get("floor", "?")
                print(f"  {t('Act','幕')}: {state.get('act','?')} ({act_name})  {t('Floor','层')}: {floor}")
                print(f"  {t('Character','角色')}: {n(p.get('name','?'))}")
                print(f"  HP: {p.get('hp','?')}/{p.get('max_hp','?')}  {t('Gold','金')}: {p.get('gold','?')}")

                deck = p.get("deck", [])
                if deck:
                    print(f"  {t('Deck','牌组')}: {len(deck)} {t('cards','张牌')}")

                relics = p.get("relics", [])
                if relics:
                    relic_names = [n(r.get("name", "?")) for r in relics]
                    print(f"  {t('Relics','遗物')} ({len(relics)}): {', '.join(relic_names)}")

                print(f"{'═' * 60}")

                if auto:
                    break

                print(f"\n  {c('q', 'cyan')} {t('Quit','退出')}    {c('n', 'cyan')} {t('New run','开始新一局')}")
                choice = input(f"  > ").strip().lower()
                if choice == "n":
                    restart_requested = True
                    break
                break

            elif dec == "map_select":
                _writeback_continue_save(send, native_save_path)
                show_map(state, send_fn=send)
                choices = state.get("choices", [])

                if auto:
                    if len(choices) == 1:
                        pick = choices[0]
                    else:
                        p = state.get("player", {})
                        hp_ratio = p.get("hp", 1) / max(p.get("max_hp", 1), 1)
                        if hp_ratio < 0.4:
                            pick = next((ch for ch in choices if ch["type"] == "RestSite"), choices[0])
                        else:
                            pick = choices[0]
                else:
                    valid = {str(i): ch for i, ch in enumerate(choices)}
                    key = get_input(t("Choose path [number]", "选择路径 [编号]"), set(valid.keys()), state=state)
                    pick = valid[key]

                state = send({"cmd": "action", "action": "select_map_node",
                             "args": {"col": pick["col"], "row": pick["row"]}})

            elif dec == "combat_play":
                show_combat(state)
                hand = state.get("hand", [])
                enemies = state.get("enemies", [])
                energy = state.get("energy", 0)

                valid = {"e": "end_turn"}
                for card in hand:
                    if card.get("can_play") and card.get("cost", 99) <= energy:
                        valid[str(card["index"])] = card
                # Add potion shortcuts
                for pot in state.get("player", {}).get("potions", []):
                    if pot:
                        valid[f"p{pot['index']}"] = f"potion_{pot['index']}"

                if auto:
                    # Auto: play first playable card, or end turn
                    playable = [c for c in hand if c.get("can_play") and c.get("cost", 99) <= energy]
                    if playable:
                        card = playable[0]
                        choice = str(card["index"])
                    else:
                        choice = "e"

                    # Stuck detection: if state fingerprint repeats, force end_turn
                    fp = (tuple(c.get("index") for c in hand), energy)
                    if fp == _auto_last_fingerprint:
                        _auto_stuck_count += 1
                        if _auto_stuck_count >= 5:
                            print(f"  {c(t('[auto] Stuck state detected, forcing end_turn','[auto] 检测到卡住状态，强制结束回合'), 'yellow')}")
                            choice = "e"
                            _auto_stuck_count = 0
                    else:
                        _auto_last_fingerprint = fp
                        _auto_stuck_count = 0
                else:
                    choice = get_input(t("Play card [index], (e)nd turn, (p0) potion", "出牌 [编号], (e)结束回合, (p0)药水"), set(valid.keys()) | {"help"}, state=state)
                    if choice == "help":
                        print(f"  {t('Enter card index, e=end turn, p0=use potion 0', '输入卡牌编号，e=结束回合，p0=使用药水0')}")
                        continue

                if choice == "e":
                    # Track hand before end_turn to detect added status cards
                    old_hand_names = [n(cd.get("name","?")) for cd in hand]
                    old_discard = state.get("discard_pile_count", 0)
                    state = send({"cmd": "action", "action": "end_turn"})
                    # Show status cards added (new cards in hand/discard that weren't there)
                    if state and state.get("decision") == "combat_play":
                        new_hand = state.get("hand", [])
                        new_discard = state.get("discard_pile_count", 0)
                        status_cards = [n(cd.get("name","?")) for cd in new_hand if cd.get("type") in ("Status", "Curse")]
                        if status_cards:
                            from collections import Counter
                            sc_str = ", ".join(f"{c(name, 'red')}" for name in status_cards)
                            print(f"  ⚠ {t('Status cards in hand:','手牌中的状态牌:')}: {sc_str}")
                elif choice.startswith("p") and choice[1:].isdigit():
                    # Use potion
                    pidx = int(choice[1:])
                    args = {"potion_index": pidx}
                    pots = state.get("player", {}).get("potions", [])
                    pot_meta = next((p for p in pots if p and p.get("index") == pidx), None)
                    if pot_meta and pot_meta.get("target_type") == "AnyEnemy" and enemies:
                        tgt = get_input(
                            t("Target enemy [index]", "选择敌人 [编号]"),
                            {str(e["index"]) for e in enemies},
                            state=state,
                        )
                        args["target_index"] = int(tgt)
                    state = send({"cmd": "action", "action": "use_potion", "args": args})
                else:
                    card = valid[choice]
                    args = {"card_index": card["index"]}
                    if card.get("target_type") == "AnyEnemy":
                        if len(enemies) == 1:
                            args["target_index"] = enemies[0]["index"]
                        elif auto:
                            args["target_index"] = min(enemies, key=lambda e: e.get("hp", 999))["index"]
                        else:
                            tgt = get_input("Target enemy [index]",
                                           {str(e["index"]) for e in enemies})
                            args["target_index"] = int(tgt)
                    state = send({"cmd": "action", "action": "play_card", "args": args})

            elif dec == "card_reward":
                show_card_reward(state)
                cards = state.get("cards", [])
                valid = {str(c["index"]): c for c in cards}
                valid["s"] = None  # skip

                if auto:
                    choice = "0" if cards else "s"
                else:
                    choice = get_input(
                        t("Reward: card index 0–n or (s)kip — see list above", "卡牌奖励：输入编号（见上方）或 (s)跳过"),
                        set(valid.keys()),
                        state=state,
                    )

                if choice == "s":
                    state = send({"cmd": "action", "action": "skip_card_reward"})
                else:
                    state = send({"cmd": "action", "action": "select_card_reward",
                                 "args": {"card_index": int(choice)}})

            elif dec == "bundle_select":
                print(f"\n{'─' * 60}")
                ctx = state.get("context", {})
                if ctx:
                    print(f"  {c(n(ctx.get('act_name','?')), 'dim')} {t('Floor','层')} {ctx.get('floor','?')}")
                print(f"  {c(t('Choose a card pack','选择一个卡牌包'), 'bold')}")
                show_player(state.get("player", {}))
                print()
                bundles = state.get("bundles", [])
                for b in bundles:
                    bidx = b["index"]
                    print(f"  {c(f'Pack [{bidx}]:', 'yellow')}")
                    for cd in b.get("cards", []):
                        _p, sf = split_card_keywords(cd.get("keywords"))
                        sp = format_card_suffix_keywords(sf)
                        print(f"    {n(cd['name'])} ({cd.get('cost','?')}) {c(cd.get('type',''), 'dim')}{sp}")
                        print_card_detail_extension(cd, indent="      ")
                valid = {str(b["index"]): b for b in bundles}
                if auto:
                    choice = "0"
                else:
                    choice = get_input(t("Choose pack [index]", "选择卡牌包 [编号]"), set(valid.keys()), state=state)
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": int(choice)}})

            elif dec == "card_select":
                print(f"\n{'─' * 60}")
                ctx = state.get("context", {})
                if ctx:
                    print(f"  {c(n(ctx.get('act_name','?')), 'dim')} {t('Floor','层')} {ctx.get('floor','?')}")
                min_sel = state.get("min_select", 1)
                max_sel = state.get("max_select", 1)
                print(f"  {c(t('Choose cards','选择卡牌'), 'bold')} — {card_pick_quantity_hint(min_sel, max_sel)}")
                show_player(state.get("player", {}))
                print()
                cards = state.get("cards", [])
                for cd in cards:
                    up = c("+", "green") if cd.get("upgraded") else ""
                    ctype_zh = CARD_TYPE_ZH.get(cd.get("type", ""), cd.get("type", ""))
                    ctype_label = t(cd.get("type", ""), ctype_zh)
                    rare = cd.get("rarity")
                    rare_part = f" {c(t(rare, RARITY_ZH.get(rare, rare)), 'dim')}" if rare else ""
                    _p, sf = split_card_keywords(cd.get("keywords"))
                    sp = format_card_suffix_keywords(sf)
                    print(f"  [{cd['index']}] {n(cd['name'])}{up} ({cd.get('cost','?')}) {c(ctype_label, 'dim')}{rare_part}{sp}")
                    print_card_detail_extension(cd, indent="      ")

                valid = {str(cd["index"]): cd for cd in cards}
                if min_sel == 0:
                    valid["s"] = None

                # Save state before selection to show diff
                old_deck_cards = [n(cd.get("name","?")) for cd in state.get("player",{}).get("deck",[])]

                if auto:
                    if not cards:
                        choice = "s" if min_sel == 0 else "0"
                    else:
                        n_pick = min(max_sel, len(cards))
                        n_pick = max(n_pick, min(min_sel, len(cards)))
                        choice = ",".join(str(cards[i]["index"]) for i in range(n_pick))
                else:
                    multi = max_sel > 1 or min_sel > 1
                    qhint = card_pick_quantity_hint(min_sel, max_sel)
                    choice = get_input(
                        t(f"Card indices, comma — {qhint} or (s)kip", f"卡牌编号逗号分隔 — {qhint}，或 (s)跳过"),
                        set(valid.keys()),
                        state=state,
                        multi_select=multi,
                        multi_min=min_sel,
                        multi_max=max_sel,
                    )

                if choice == "s":
                    state = send({"cmd": "action", "action": "skip_select"})
                else:
                    # Support comma-separated indices
                    state = send({"cmd": "action", "action": "select_cards",
                                 "args": {"indices": choice}})

                # Show what changed
                if state and state.get("player"):
                    from collections import Counter
                    new_deck_cards = [n(cd.get("name","?")) for cd in state["player"].get("deck",[])]
                    added = Counter(new_deck_cards) - Counter(old_deck_cards)
                    removed = Counter(old_deck_cards) - Counter(new_deck_cards)
                    if added or removed:
                        parts = []
                        for card_name, cnt in removed.items():
                            parts.append(c(f"-{card_name}" + (f"x{cnt}" if cnt > 1 else ""), "red"))
                        for card_name, cnt in added.items():
                            parts.append(c(f"+{card_name}" + (f"x{cnt}" if cnt > 1 else ""), "green"))
                        print(f"\n  {c(t('Changes:','变化:'), 'yellow')} {t('Deck','牌组')}: {' '.join(parts)}")

            elif dec == "shop":
                show_shop(state)

                if auto:
                    choice = "leave"
                else:
                    choice = get_input(t("Buy [index/r0/p0/rm] or (leave)", "购买 [编号/r0/p0/rm] 或 (leave)离开"), state=state)

                if choice == "leave":
                    state = send({"cmd": "action", "action": "leave_room"})
                elif choice == "rm":
                    state = send({"cmd": "action", "action": "remove_card"})
                elif choice.startswith("r"):
                    state = send({"cmd": "action", "action": "buy_relic",
                                 "args": {"relic_index": int(choice[1:])}})
                elif choice.startswith("p"):
                    state = send({"cmd": "action", "action": "buy_potion",
                                 "args": {"potion_index": int(choice[1:])}})
                else:
                    state = send({"cmd": "action", "action": "buy_card",
                                 "args": {"card_index": int(choice)}})

            elif dec == "rest_site":
                show_rest_site(state)
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled")]
                valid = {str(o["index"]): o for o in enabled}

                if auto:
                    hp = state.get("player", {}).get("hp", 1)
                    mhp = state.get("player", {}).get("max_hp", 1)
                    heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
                    smith = next((o for o in enabled if o.get("option_id") == "SMITH"), None)
                    pick = (heal if hp < mhp * 0.7 else smith) or (heal or (enabled[0] if enabled else None))
                    choice = str(pick["index"]) if pick else "0"
                else:
                    choice = get_input(t("Choose option [index]", "选择 [编号]"), set(valid.keys()), state=state)

                state = send({"cmd": "action", "action": "choose_option",
                             "args": {"option_index": int(choice)}})
                if state and state.get("type") == "error":
                    state = send({"cmd": "action", "action": "leave_room"})

            elif dec == "event_choice":
                show_event(state)
                options = state.get("options", [])
                unlocked = [o for o in options if not o.get("is_locked")]
                valid = {str(o["index"]): o for o in unlocked}
                valid["leave"] = None

                # Save state before choice to show diff
                old_relics = set(n(r.get("name","?")) for r in state.get("player",{}).get("relics",[]))
                old_deck_cards = [n(cd.get("name","?")) for cd in state.get("player",{}).get("deck",[])]
                old_deck = state.get("player",{}).get("deck_size", 0)
                old_hp = state.get("player",{}).get("hp", 0)
                old_max_hp = state.get("player",{}).get("max_hp", 0)
                old_gold = state.get("player",{}).get("gold", 0)

                if auto:
                    choice = str(unlocked[0]["index"]) if unlocked else "leave"
                else:
                    choice = get_input(t("Choose option [index] or (leave)", "选择 [编号] 或 (leave)离开"), set(valid.keys()), state=state)

                if choice == "leave":
                    state = send({"cmd": "action", "action": "leave_room"})
                else:
                    state = send({"cmd": "action", "action": "choose_option",
                                 "args": {"option_index": int(choice)}})
                    if state and state.get("type") == "error":
                        state = send({"cmd": "action", "action": "leave_room"})

                # Show what changed
                if state and state.get("player"):
                    new_p = state["player"]
                    new_relics = set(n(r.get("name","?")) for r in new_p.get("relics",[]))
                    gained_relics = new_relics - old_relics
                    new_deck_cards = [n(cd.get("name","?")) for cd in new_p.get("deck",[])]
                    new_deck = new_p.get("deck_size", 0)
                    new_hp = new_p.get("hp", 0)
                    new_max_hp = new_p.get("max_hp", 0)
                    new_gold = new_p.get("gold", 0)
                    changes = []
                    if gained_relics:
                        changes.append(f"{t('Relic','遗物')}: {', '.join(gained_relics)}")
                    # Show specific card changes
                    from collections import Counter
                    old_counts = Counter(old_deck_cards)
                    new_counts = Counter(new_deck_cards)
                    added = new_counts - old_counts
                    removed = old_counts - new_counts
                    if added or removed:
                        parts = []
                        for card_name, cnt in removed.items():
                            parts.append(c(f"-{card_name}" + (f"x{cnt}" if cnt > 1 else ""), "red"))
                        for card_name, cnt in added.items():
                            parts.append(c(f"+{card_name}" + (f"x{cnt}" if cnt > 1 else ""), "green"))
                        changes.append(f"{t('Deck','牌组')}: {' '.join(parts)}")
                    elif new_deck != old_deck:
                        changes.append(f"{t('Deck','牌组')}: {old_deck} → {new_deck}")
                    if new_hp != old_hp or new_max_hp != old_max_hp:
                        changes.append(f"{t('HP','生命')}: {old_hp}/{old_max_hp} → {new_hp}/{new_max_hp}")
                    if new_gold != old_gold:
                        diff = new_gold - old_gold
                        changes.append(f"{t('Gold','金')}: {'+' if diff > 0 else ''}{diff}")
                    if changes:
                        print(f"\n  {c(t('Changes:','变化:'), 'yellow')} {'; '.join(changes)}")

            else:
                print(f"  {t('Unknown state:','未知状态:')} {dec}")
                state = send({"cmd": "action", "action": "proceed"})

    except _QuitRequested:
        quit_sent = False
        quit_save_path = _quit_with_save(native_save_path, character, actual_seed)
        # Retry loop: if save fails the process stays alive so we can try a different path.
        quit_sent = True
        while True:
            quit_cmd = {"cmd": "quit"}
            if quit_save_path:
                quit_cmd["path"] = quit_save_path
            result = send(quit_cmd)
            if result and result.get("type") == "save_error":
                save_detail = result.get("save") or {}
                msg = save_detail.get("message", "?")
                print(f"  {c(t('Save failed:','存档失败:'), 'red')} {msg}")
                try:
                    ans = input(f"  {t('New path (Enter = quit without saving): ','新路径（回车则不保存退出）: ')}").strip()
                except (EOFError, KeyboardInterrupt):
                    ans = ""
                quit_save_path = ans if ans else None
            else:
                _show_quit_save_result(result)
                break
    except KeyboardInterrupt:
        print(f"\n  {c(t('Run abandoned.','已放弃本次运行。'), 'yellow')}")
    finally:
        if not quit_sent:
            try:
                result = send({"cmd": "quit"})
                _show_quit_save_result(result)
            except Exception:
                pass
        logger.close()
        if logger.path:
            print(f"\n  [log] {t('Game log saved to','游戏日志已保存至')} {logger.path}")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    return restart_requested


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play Slay the Spire 2 in your terminal")
    parser.add_argument("--auto", action="store_true", help="Auto-play with simple AI")
    parser.add_argument("--seed", type=str, default=None, help="Random seed")
    parser.add_argument("--character", type=str, default="Ironclad",
                       choices=["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"],
                       help="Character to play")
    parser.add_argument("--ascension", type=int, default=0,
                       choices=range(0, 11), metavar="0-10",
                       help="Ascension level (0-10)")
    parser.add_argument("--lang", type=str, default="zh",
                       choices=["en", "zh", "both"],
                       help="Display language: en, zh, or both")
    parser.add_argument("--no-log", action="store_true",
                       help="Disable game logging")
    parser.add_argument("--load", type=str, default=None,
                       help="Load a save file (action replay)")
    parser.add_argument("--saves", action="store_true",
                       help="List available saves and exit")
    parser.add_argument("--save-info", type=str, default=None,
                       help="Show info from a save file (provide path)")
    parser.add_argument("--continue", dest="continue_save", type=str, default=None,
                       help="Continue playing from a save file (provide path)")
    args = parser.parse_args()

    LANG = args.lang

    # Mutual exclusion: conflicting flags
    if args.load is not None:
        if args.saves:
            parser.error("Cannot combine --load with --saves")
        if args.save_info is not None:
            parser.error("Cannot combine --load with --save-info")
        if args.continue_save is not None:
            parser.error("Cannot combine --load with --continue")
    if args.saves:
        if args.save_info is not None:
            parser.error("Cannot combine --saves with --save-info")
        if args.continue_save is not None:
            parser.error("Cannot combine --saves with --continue")
    if args.save_info is not None:
        if args.continue_save is not None:
            parser.error("Cannot combine --save-info with --continue")

    if args.save_info is not None:
        p = args.save_info
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        if not os.path.isfile(p):
            print(f"Save file not found: {p}")
            sys.exit(1)
        show_native_save(p)
        sys.exit(0)

    if args.saves:
        saves = _list_saves()
        if saves:
            print(f"\n{'─' * 50}")
            for s in saves:
                stype = s.get("type", "replay")
                if stype == "native":
                    print(f"  {s['file']}  [{t('native save','原生存档')}]")
                else:
                    print(f"  {s['file']}  {s['character']}  {t('seed','种子')}:{s['seed']}  {t('actions','步操作')}:{s['actions']}")
            print(f"{'─' * 50}")
            print(f"  {t('Replay saves:','回放存档:')} python3 play.py --load saves/<file>")
            print(f"  {t('Native saves:','原生存档:')} python3 play.py --continue saves/<file>")
        else:
            print(t("No saves found.", "没有找到存档。"))
        sys.exit(0)

    load_path = None
    if args.load:
        p = args.load
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        if not os.path.isfile(p):
            print(f"Save file not found: {args.load}")
            sys.exit(1)
        load_path = p

    native_save_path = None
    if args.continue_save is not None:
        native_save_path = args.continue_save
        if not os.path.isabs(native_save_path):
            native_save_path = os.path.join(ROOT, native_save_path)
        if not os.path.isfile(native_save_path):
            print(f"Save file not found: {native_save_path}")
            sys.exit(1)
        show_native_save(native_save_path)

    ensure_setup()
    next_seed = args.seed
    next_auto = args.auto
    next_load_path = load_path
    next_native_save_path = native_save_path
    while True:
        restart = play(character=args.character, seed=next_seed, auto=next_auto,
                       ascension=args.ascension, log=not args.no_log,
                       load_path=next_load_path,
                       native_save_path=next_native_save_path)
        if not restart:
            break
        next_seed = None
        next_auto = False
        next_load_path = None
        next_native_save_path = None
