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
import re
import subprocess
import sys
import os
import argparse
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(ROOT, "Sts2Headless", "Sts2Headless.csproj")
LIB_DIR = os.path.join(ROOT, "lib")

def _find_dotnet():
    """Find .NET SDK binary."""
    candidates = [
        os.path.expanduser("~/.dotnet-arm64/dotnet"),
        os.path.expanduser("~/.dotnet/dotnet"),
        "dotnet",
    ]
    for p in candidates:
        try:
            r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None

DOTNET = _find_dotnet()


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

    # Set STS2_GAME_DIR env var for runtime DLL resolution
    game_dir = _find_game_dir()
    if game_dir:
        os.environ["STS2_GAME_DIR"] = game_dir

    # Check if built
    exe_dir = os.path.join(ROOT, "Sts2Headless", "bin", "Debug", "net9.0")
    exe = os.path.join(exe_dir, "Sts2Headless.dll")
    if not os.path.isfile(exe) or os.path.getmtime(sts2_dll) > os.path.getmtime(exe):
        print("🏗️  Building...")
        if not _build():
            print("❌ Build failed. Try: ./setup.sh")
            sys.exit(1)
        print("  ✓ Build succeeded")

# Language setting (set by --lang flag)
LANG = "zh"  # "en", "zh", or "both"

# ─── Display helpers ───

def n(obj):
    """Extract display name based on language setting."""
    if isinstance(obj, dict):
        if "en" in obj:
            en = obj["en"]
            zh = obj.get("zh")
            if LANG == "zh" and zh:
                return zh
            elif LANG == "en":
                return en
            elif zh and zh != en:
                return f"{en}({zh})"
            return en
    return str(obj)

def short_n(obj):
    """Short English name only."""
    if isinstance(obj, dict) and "en" in obj:
        return obj["en"]
    return str(obj)

def desc(obj):
    """Extract description, strip BBCode tags, clean SmartFormat vars."""
    if isinstance(obj, dict) and "en" in obj:
        import re
        if LANG == "zh" and obj.get("zh"):
            text = obj["zh"]
        elif LANG == "en":
            text = obj["en"]
        else:
            text = obj.get("zh") or obj.get("en") or ""
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
    "orange": "\033[33m",
    "bold": "\033[1m", "dim": "\033[2m", "underline": "\033[4m", "reset": "\033[0m",
}

def c(text, color):
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"

def cu(text, color=None):
    """Color + underline — used for available choice labels."""
    return f"{COLORS['underline']}{COLORS.get(color, '')}{text}{COLORS['reset']}"

def bar(current, maximum, width=20):
    filled = int(current / max(maximum, 1) * width)
    return c("█" * filled, "red") + c("░" * (width - filled), "dim")

def t(en, zh=None):
    """Translate UI string based on LANG setting."""
    if zh is None:
        return en
    if LANG == "zh":
        return zh
    elif LANG == "en":
        return en
    return en

RARITY_ZH = {"Common": "普通", "Uncommon": "罕见", "Rare": "稀有"}
CARD_TYPE_ZH = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态", "Curse": "诅咒"}
NODE_TYPE_ZH = {"Monster": "怪物", "Elite": "精英", "Boss": "Boss", "RestSite": "休息处",
                "Shop": "商店", "Treasure": "宝箱", "Event": "事件", "Unknown": "未知", "Ancient": "远古"}

NODE_COLORS = {
    "Elite": "magenta", "RestSite": "green", "Shop": "yellow",
    "Treasure": "orange", "Event": "blue", "Unknown": "blue",
    "Ancient": "orange",
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
        kl = key.lower()
        val = lower_vars.get(kl)
        if val is not None:
            if isinstance(val, dict) and ("en" in val or "zh" in val):
                return n(val)
            return str(val)
        # Special vars
        if kl == "energyprefix":
            return ""  # prefix only, unit already added by energyIcons handler in desc()
        return f"[{key}]"
    return re.sub(r'\[(\w+)\]', replacer, text)

def card_desc(card):
    """Get resolved card description using stats as template vars."""
    d = desc(card.get("description", {}))
    stats = card.get("stats") or {}
    return resolve_template(d, stats)  # always resolve (handles energyPrefix etc.)

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
        idx = p.get("index", 0) + 1
        return f"[{idx}] {name}" + (f": {c(d, 'dim')}" if d else "")
    return n(p)

def show_player(p, show_deck=False):
    hp, mhp = p.get("hp", 0), p.get("max_hp", 1)
    blk = p.get("block", 0)
    gold = p.get("gold", 0)
    deck = p.get("deck_size", 0)
    name = n(p.get("name", "?"))

    print(f"  {c(name, 'bold')}  HP {bar(hp, mhp)} {c(f'{hp}/{mhp}', 'red')}"
          + (f"  {c(str(blk), 'blue')}{t('blk','挡')}" if blk > 0 else "")
          + f"  {t('Gold','金')}{c(str(gold), 'yellow')}  {t('Deck','牌组')}{deck}")
    for r in p.get("relics", []):
        print(f"    🔶 {relic_str(r)}")
    for pot in p.get("potions", []):
        if pot:
            print(f"    🧪 {potion_str(pot)}")
    if show_deck:
        cards = p.get("deck", [])
        if cards:
            print(f"  {c(t('Deck:','牌组:'), 'bold')}")
            KW_ZH = {"Exhaust": "消耗", "Innate": "固有", "Ethereal": "虚无", "Retain": "保留", "Sly": "奇巧", "Eternal": "永恒", "Unplayable": "不能被打出"}
            for cd in cards:
                up = c("+", "green") if cd.get("upgraded") else ""
                ctype_zh = CARD_TYPE_ZH.get(cd.get("type",""), cd.get("type",""))
                kws = cd.get("keywords") or []
                kw_str = " ".join(c(t(k, KW_ZH.get(k, k)), "dim") for k in kws)
                kw_str = f" [{kw_str}]" if kw_str else ""
                cd_d = card_desc(cd)
                print(f"    {n(cd['name'])}{up} ({cd.get('cost','?')}) {c(t(cd.get('type',''), ctype_zh), 'dim')}{kw_str}")
                if cd_d:
                    print(f"      {c(cd_d, 'dim')}")
                stats = cd.get("stats") or {}
                aug_parts = _format_upgrade_preview(stats, cd.get("after_upgrade"), cd.get("cost"))
                if aug_parts:
                    print(f"      {c(t('upgrade:','升级:'), 'green')} {', '.join(aug_parts)}")

def show_combat(state):
    rnd = state.get("round", 0)
    energy = state.get("energy", 0)
    max_energy = state.get("max_energy", 0)
    draw = state.get("draw_pile_count", 0)
    discard = state.get("discard_pile_count", 0)

    print(f"\n{'─' * 60}")
    print(f"  {c(t(f'Round {rnd}',f'回合 {rnd}'), 'bold')}  {t('Energy','能量')}{c(f'{energy}/{max_energy}', 'cyan')}  {t('Draw','抽牌')}{draw}  {t('Discard','弃牌')}{discard}")
    show_player(state.get("player", {}))

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
            pw_parts = [f"{n(pw['name'])}{pw.get('amount','')}" for pw in powers]
            power_str = "  " + c(" ".join(pw_parts), "dim")

        print(f"  [{e['index']+1}] {n(e['name'])}  {bar(hp, mhp)} {hp}/{mhp}"
              + (f"  {c(str(blk), 'blue')}{t('blk','挡')}" if blk else "")
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

        # Show damage/block inline, plus description for non-trivial cards
        stats = card.get("stats") or {}
        stat_parts = []
        if "damage" in stats: stat_parts.append(c(f"{stats['damage']}{t('dmg','伤')}", "red"))
        if "block" in stats: stat_parts.append(c(f"{stats['block']}{t('blk','挡')}", "blue"))
        stat_str = " ".join(stat_parts)

        # Show description if card has no damage/block (so effect isn't obvious from stats)
        cd_d = card_desc(card)
        extra_desc = ""
        if cd_d and "damage" not in stats and "block" not in stats:
            # No damage/block — show full description inline
            extra_desc = f"  {c(cd_d.replace(chr(10), ' '), 'dim')}"
        elif cd_d and any(k not in ("damage", "block") for k in stats):
            # Has extra effects beyond damage/block — show last line
            lines = cd_d.split("\n")
            if len(lines) > 1:
                extra_desc = f"  {c(lines[-1], 'dim')}"

        # Show keywords (Innate, Exhaust, Ethereal, etc.)
        KW_ZH = {"Exhaust": "消耗", "Innate": "固有", "Ethereal": "虚无", "Retain": "保留", "Sly": "奇巧", "Eternal": "永恒", "Unplayable": "不能被打出"}
        kws = card.get("keywords") or []
        kw_str = " ".join(c(t(k, KW_ZH.get(k, k)), "dim") for k in kws) if kws else ""
        if kw_str: kw_str = f" [{kw_str}]"
        ench = card.get("enchantment")
        ench_str = f" {c(n(ench), 'magenta')}" if ench else ""

        print(f"  {mark} [{card['index']+1}] {c(n(card['name']), type_color)}{ench_str} ({cost_str}) {stat_str}{kw_str}{extra_desc}"
              + (f"  {c('→','yellow')}" if target == "AnyEnemy" else ""))

def show_map(state, send_fn=None):
    """Show map at map_select. Fetches full map if send_fn available."""
    choices = sorted(state.get("choices", []), key=lambda ch: ch["col"])
    choice_set = {(ch["col"], ch["row"]) for ch in choices}

    # Try to fetch full map for richer display
    if send_fn:
        map_data = send_fn({"cmd": "get_map"})
        if map_data and map_data.get("type") == "map":
            _render_map(map_data, choice_set)
            # Print available choices below the map
            type_icons = {
                "Monster": "⚔", "Elite": "💀", "Boss": "👹",
                "RestSite": "🏕", "Shop": "🏪", "Treasure": "💎",
                "Event": "❓", "Unknown": "❓", "Ancient": "🏛",
            }
            print(f"  {c(t('Available paths:','可选路径:'), 'bold')}")
            for i, ch in enumerate(choices, 1):
                icon = type_icons.get(ch["type"], "?")
                ntype = t(ch["type"], NODE_TYPE_ZH.get(ch["type"], ch["type"]))
                col = NODE_COLORS.get(ch["type"])
                label = c(f"{icon} {ntype}", col) if col else f"{icon} {ntype}"
                print(f"    [{i}] {label}  ({t('col','列')}{ch['col']}, {t('row','行')}{ch['row']})")
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
    for i, ch in enumerate(choices, 1):
        icon = type_icons.get(ch["type"], "?")
        ntype = t(ch["type"], NODE_TYPE_ZH.get(ch["type"], ch["type"]))
        col = NODE_COLORS.get(ch["type"])
        label = c(f"{icon} {ntype}", col) if col else f"{icon} {ntype}"
        print(f"  [{i}] {label}")

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
    KW_ZH = {"Exhaust": "消耗", "Innate": "固有", "Ethereal": "虚无", "Retain": "保留", "Sly": "奇巧", "Eternal": "永恒", "Unplayable": "不能被打出"}
    for kw in (aug.get("removed_keywords") or []):
        parts.append(c(f"-{t(kw, KW_ZH.get(kw, kw))}", "green"))
    for kw in (aug.get("added_keywords") or []):
        parts.append(c(f"+{t(kw, KW_ZH.get(kw, kw))}", "yellow"))
    return parts

def show_card_reward(state):
    print(f"\n{'─' * 60}")
    gold_earned = state.get("gold_earned", 0)
    if gold_earned > 0:
        print(f"  {c(t('Combat won!','战斗胜利!'), 'green')} +{c(str(gold_earned), 'yellow')}{t('g','金')}")
    print(f"  {c(t('Card Reward','卡牌奖励'), 'bold')} — {t('choose one (or skip)','选一张（或跳过）')}")
    show_player(state.get("player", {}))
    print()
    for card in state.get("cards", []):
        ctype = card.get("type", "?")
        rarity = card.get("rarity", "Common")
        cost = card.get("cost", "?")
        type_color = {"Attack": "red", "Skill": "blue", "Power": "magenta"}.get(ctype, "reset")
        rarity_zh = RARITY_ZH.get(rarity, rarity)
        rarity_label = t(rarity, rarity_zh)
        rarity_color = {"Rare": "yellow", "Uncommon": "cyan"}.get(rarity, "dim")
        stats = card.get("stats") or {}
        cd_desc = card_desc(card)

        print(f"  [{card['index']+1}] {c(n(card['name']), type_color)} ({cost}) {c(rarity_label, rarity_color)}")
        if cd_desc:
            print(f"      {c(cd_desc, 'dim')}")
        # Show upgrade preview
        aug_parts = _format_upgrade_preview(stats, card.get("after_upgrade"), card.get("cost"))
        if aug_parts:
            print(f"      {c(t('upgrade:','升级:'), 'green')} {', '.join(aug_parts)}")

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
        cd = card_desc(card)
        desc_str = f" — {c(cd, 'dim')}" if cd else ""
        print(f"  [{card['index']+1}] {n(card['name'])} ({t(card.get('type','?'), ctype_zh)}){desc_str} — {affordable}{t('g','金')}{sale}")

    print(f"\n  {c(t('Relics:','遗物:'), 'bold')}")
    for r in state.get("relics", []):
        if not r.get("is_stocked"): continue
        cost = r.get("cost", 0)
        affordable = c(str(cost), "green") if cost <= gold else c(str(cost), "red")
        d = desc(r.get("description", {}))
        d = resolve_template(d, r.get("vars") or {})
        desc_str = f": {c(d, 'dim')}" if d else ""
        print(f"  [r{r['index']+1}] {n(r['name'])}{desc_str} — {affordable}{t('g','金')}")

    print(f"\n  {c(t('Potions:','药水:'), 'bold')}")
    for p in state.get("potions", []):
        if not p.get("is_stocked"): continue
        cost = p.get("cost", 0)
        affordable = c(str(cost), "green") if cost <= gold else c(str(cost), "red")
        d = desc(p.get("description", {}))
        d = resolve_template(d, p.get("vars") or {})
        desc_str = f": {c(d, 'dim')}" if d else ""
        print(f"  [p{p['index']+1}] {n(p['name'])}{desc_str} — {affordable}{t('g','金')}")

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
        print(f"  {mark} [{opt['index']+1}] {opt_name}" + (f" — {opt_desc}" if opt_desc and opt_desc != opt_id else ""))

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
                        except: pass
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
        if isinstance(raw_desc, dict):
            opt_desc = desc(raw_desc)
        elif raw_desc:
            opt_desc = loc_resolve(raw_desc) if '.' in str(raw_desc) or str(raw_desc).isupper() else raw_desc
        else:
            opt_desc = ""
        # Resolve template vars like [MaxHp], [Gold]
        opt_vars = opt.get("vars") or {}
        if opt_vars and opt_desc:
            opt_desc = resolve_template(opt_desc, opt_vars)
        desc_str = f" — {c(opt_desc, 'dim')}" if opt_desc else ""
        print(f"  {mark} [{opt['index']+1}] {title}{desc_str}")

# ─── Input handling ───

def _render_map(map_data, choice_set=None):
    """Render map as a grid with connection lines between rows."""
    if choice_set is None:
        choice_set = set()

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

    # Boss name header
    boss = map_data.get("boss", {})
    boss_name = n(boss.get("name")) if boss.get("name") else None
    if boss_name:
        print(f"  {c('B', 'red')}={t('Boss','Boss')}: {c(boss_name, 'red')}")
    print(f"  {'─' * width}")

    # Boss row
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
            ntype = nd.get("type", "?")
            icon = ICONS.get(ntype, "·")
            node_color = NODE_COLORS.get(ntype)
            is_cur = (cur and cur["col"] == col and cur["row"] == rn)
            is_choice = (col, rn) in choice_set
            visited = nd.get("visited", False)

            center = col * W + W // 2
            if is_cur:
                buf[center - 1] = "["
                buf[center] = icon
                buf[center + 1] = "]"
                color_subs.append((center - 1, center + 2, c(f"[{icon}]", "green")))
            elif is_choice:
                buf[center] = icon
                color_subs.append((center, center + 1, cu(icon, node_color)))
            elif visited:
                buf[center] = icon
                color_subs.append((center, center + 1, c(icon, "dim")))
            elif node_color:
                buf[center] = icon
                color_subs.append((center, center + 1, c(icon, node_color)))
            else:
                buf[center] = icon

        line = "".join(buf)
        # Apply colors right-to-left
        for start, end, colored in sorted(color_subs, key=lambda x: -x[0]):
            line = line[:start] + colored + line[end:]
        print(f"  {rn:>2}| {line}")

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
    legend = (f"  M={t('Monster','怪')} {c('E','magenta')}={t('Elite','英')} {c('R','green')}={t('Rest','休')}"
              f" {c('$','yellow')}={t('Shop','店')} {c('T','orange')}={t('Treasure','宝')}"
              f" {c('?','blue')}={t('Event','事')} {c('A','orange')}={t('Ancient','远古')}"
              f" {c('[x]','green')}={t('You','你')} {cu('x')}={t('Next','可选')}")
    print(legend)
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

def _handle_meta(raw, state=None):
    """Handle meta-commands (help, map, deck, potions, relics, quit).
    Returns True if the command was handled (caller should continue loop), False otherwise."""
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

  {c('操作:', 'bold')}
    地图:    输入路径编号 (1, 2, 3)
    战斗:    卡牌编号 / {c('e', 'yellow')} 结束回合 / {c('p1', 'yellow')} 使用药水
    奖励:    卡牌编号 / {c('s', 'yellow')} 跳过
    休息:    选项编号
    事件:    选项编号 / {c('leave', 'yellow')} 离开
    商店:    {c('c1', 'yellow')} 买卡 / {c('r1', 'yellow')} 遗物 / {c('p1', 'yellow')} 药水 / {c('rm', 'yellow')} 移除 / {c('leave', 'yellow')} 离开
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

  {c('Actions:', 'bold')}
    Map:     path number (1, 2, 3)
    Combat:  card index / {c('e', 'yellow')} end turn / {c('p1', 'yellow')} use potion
    Reward:  card index / {c('s', 'yellow')} skip
    Rest:    option index
    Event:   option index / {c('leave', 'yellow')} leave
    Shop:    {c('c1', 'yellow')} card / {c('r1', 'yellow')} relic / {c('p1', 'yellow')} potion / {c('rm', 'yellow')} remove / {c('leave', 'yellow')} leave
""")
        return True
    if raw == "deck" and state:
        show_player(state.get("player", {}), show_deck=True)
        return True
    if raw == "potions" and state:
        pots = state.get("player", {}).get("potions", [])
        if pots:
            for pot in pots:
                if pot: print(f"  🧪 {potion_str(pot)}")
        else:
            print(f"  {t('No potions.','没有药水。')}")
        return True
    if raw == "relics" and state:
        for r in state.get("player", {}).get("relics", []):
            print(f"  🔶 {relic_str(r)}")
        return True
    if raw == "map":
        if hasattr(get_input, '_send'):
            map_data = get_input._send({"cmd": "get_map"})
            if map_data and map_data.get("type") == "map":
                # Build choice_set: use state choices if at map_select, else
                # derive from current node's children in the map data
                choice_set = set()
                if state and state.get("decision") == "map_select":
                    for ch in state.get("choices", []):
                        choice_set.add((ch["col"], ch["row"]))
                else:
                    cur = map_data.get("current_coord")
                    if cur:
                        for row in map_data.get("rows", []):
                            for nd in row:
                                if nd.get("col") == cur["col"] and nd.get("row") == cur["row"]:
                                    for child in (nd.get("children") or []):
                                        choice_set.add((child["col"], child["row"]))
                _render_map(map_data, choice_set)
            else:
                print("  Map not available.")
        elif state:
            ctx = state.get("context", {})
            print(f"  {c(n(ctx.get('act_name','?')), 'bold')} Floor {ctx.get('floor','?')}")
        return True
    if raw == "quit":
        print(t("Quitting...","退出..."))
        sys.exit(0)
    return False

def get_input(prompt, valid_options=None, state=None):
    """Get user input with validation. Supports meta-commands: help, map, deck, potions."""
    while True:
        try:
            raw = input(f"\n{c('>', 'green')} {prompt}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{t('Quitting...','退出...')}")
            sys.exit(0)

        if not raw:
            continue
        if _handle_meta(raw, state):
            continue
        if valid_options and raw not in valid_options:
            print(f"  {t('Invalid. Options:','无效。选项:')} {', '.join(sorted(valid_options))}")
            continue
        return raw

# ─── Main game loop ───

def play(character="Ironclad", seed=None, auto=False, ascension=0):
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
                return json.loads(l)

    def send(cmd):
        proc.stdin.write(json.dumps(cmd) + "\n")
        proc.stdin.flush()
        return read()

    # Wire send into get_input for map command
    get_input._send = send

    try:
        ready = read()
        if not ready:
            print("Failed to start simulator")
            return

        print(f"\n{c('Slay the Spire 2 — Headless CLI', 'bold')}")
        asc_str = f"  {t('Ascension','进阶')}: {ascension}" if ascension > 0 else ""
        print(f"{t('Character','角色')}: {character}  {t('Seed','种子')}: {seed or t('random','随机')}{asc_str}")
        print(f"{t('Type','输入')} {c('help', 'cyan')} {t('for available commands.','查看可用命令。')}\n")

        state = send({"cmd": "start_run", "character": character, "ascension": ascension, "seed": seed or f"cli_{random.randint(1000,9999)}"})

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
                print(f"\n{'═' * 60}")
                if victory:
                    print(f"  {c(t('VICTORY!','胜利!'), 'green')}")
                else:
                    print(f"  {c(t('DEFEAT','战败'), 'red')} Act {state.get('act')}, {t('Floor','层')} {state.get('floor')}")
                show_player(p)
                print(f"{'═' * 60}")
                break

            elif dec == "map_select":
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
                    valid = {str(i): ch for i, ch in enumerate(choices, 1)}
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
                        valid[str(card["index"]+1)] = card
                # Add potion shortcuts
                for pot in state.get("player", {}).get("potions", []):
                    if pot:
                        valid[f"p{pot['index']+1}"] = pot

                if auto:
                    # Auto: play first playable card, or end turn
                    playable = [c for c in hand if c.get("can_play") and c.get("cost", 99) <= energy]
                    if playable:
                        card = playable[0]
                        choice = str(card["index"]+1)
                    else:
                        choice = "e"
                else:
                    choice = get_input(t("Play card [index], (e)nd turn, (p1) potion", "出牌 [编号], (e)结束回合, (p1)药水"), set(valid.keys()) | {"help"}, state=state)
                    if choice == "help":
                        print(f"  {t('Enter card index, e=end turn, p1=use potion 1', '输入卡牌编号，e=结束回合，p1=使用药水1')}")
                        continue

                if choice == "e":
                    state = send({"cmd": "action", "action": "end_turn"})
                elif choice.startswith("p") and choice[1:].isdigit():
                    # Use potion — user typed 1-based, look up the potion object for engine index
                    pot = valid[choice]
                    args = {"potion_index": pot["index"]}
                    # Ask for target if needed
                    if enemies:
                        tgt = get_input(t("Target enemy [index] or self (s)", "目标敌人 [编号] 或 自身 (s)"),
                                        {str(e["index"]+1) for e in enemies} | {"s"}, state=state)
                        if tgt != "s" and tgt.isdigit():
                            args["target_index"] = int(tgt) - 1
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
                            tgt = get_input(t("Target enemy [index]", "目标敌人 [编号]"),
                                           {str(e["index"]+1) for e in enemies})
                            args["target_index"] = int(tgt) - 1
                    state = send({"cmd": "action", "action": "play_card", "args": args})

            elif dec == "card_reward":
                show_card_reward(state)
                cards = state.get("cards", [])
                valid = {str(c["index"]+1): c for c in cards}
                valid["s"] = None  # skip

                if auto:
                    choice = str(cards[0]["index"]+1) if cards else "s"
                else:
                    choice = get_input(t("Pick card [index] or (s)kip", "选择卡牌 [编号] 或 (s)跳过"), set(valid.keys()), state=state)

                if choice == "s":
                    state = send({"cmd": "action", "action": "skip_card_reward"})
                else:
                    state = send({"cmd": "action", "action": "select_card_reward",
                                 "args": {"card_index": valid[choice]["index"]}})

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
                    bidx = b["index"] + 1
                    print(f"  {c(f'Pack [{bidx}]:', 'yellow')}")
                    for cd in b.get("cards", []):
                        cd_desc = card_desc(cd)
                        print(f"    {n(cd['name'])} ({cd.get('cost','?')}) {c(cd.get('type',''), 'dim')}")
                        if cd_desc:
                            print(f"      {c(cd_desc, 'dim')}")
                valid = {str(b["index"]+1): b for b in bundles}
                if auto:
                    choice = str(bundles[0]["index"]+1) if bundles else "1"
                else:
                    choice = get_input(t("Choose pack [index]", "选择卡牌包 [编号]"), set(valid.keys()), state=state)
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": valid[choice]["index"]}})

            elif dec == "card_select":
                print(f"\n{'─' * 60}")
                ctx = state.get("context", {})
                if ctx:
                    print(f"  {c(n(ctx.get('act_name','?')), 'dim')} {t('Floor','层')} {ctx.get('floor','?')}")
                min_sel = state.get("min_select", 1)
                max_sel = state.get("max_select", 1)
                print(f"  {c(t('Choose cards','选择卡牌'), 'bold')} ({t('select','选择')} {min_sel}-{max_sel})")
                show_player(state.get("player", {}))
                print()
                cards = state.get("cards", [])
                for cd in cards:
                    up = c("+", "green") if cd.get("upgraded") else ""
                    stats = cd.get("stats") or {}
                    ctype_zh = CARD_TYPE_ZH.get(cd.get("type", ""), cd.get("type", ""))
                    ctype_label = t(cd.get("type", ""), ctype_zh)
                    cd_desc_text = card_desc(cd)
                    print(f"  [{cd['index']+1}] {n(cd['name'])}{up} ({cd.get('cost','?')}) {c(ctype_label, 'dim')}")
                    if cd_desc_text:
                        print(f"      {c(cd_desc_text, 'dim')}")
                    aug_parts = _format_upgrade_preview(stats, cd.get("after_upgrade"), cd.get("cost"))
                    if aug_parts:
                        print(f"      {c(t('upgrade:','升级:'), 'green')} {', '.join(aug_parts)}")

                valid = {str(cd["index"]+1): cd for cd in cards}

                if auto:
                    choice_tokens = [str(cards[0]["index"]+1)] if cards else []
                    skip = not choice_tokens
                else:
                    skip = False
                    choice_tokens = []
                    can_skip = min_sel == 0
                    skip_hint = " or (s)kip" if can_skip else ""
                    skip_hint_zh = "，或 (s) 跳过" if can_skip else ""
                    prompt_str = t(
                        f"Choose {min_sel}-{max_sel} card(s) [index], comma/space separated{skip_hint}",
                        f"选择 {min_sel}-{max_sel} 张卡牌 [编号]，逗号或空格分隔{skip_hint_zh}"
                    )
                    while True:
                        try:
                            raw = input(f"\n{c('>', 'green')} {prompt_str}: ").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            print(f"\n{t('Quitting...','退出...')}")
                            sys.exit(0)
                        if not raw:
                            continue
                        if _handle_meta(raw, state):
                            continue
                        if can_skip and raw == "s":
                            skip = True
                            break
                        tokens = [tok for tok in re.split(r'[,\s]+', raw) if tok]
                        invalid = [tok for tok in tokens if tok not in valid]
                        if invalid:
                            print(f"  {t('Invalid indices:','无效编号:')} {', '.join(invalid)}. "
                                  f"{t('Valid:','可选:')} {', '.join(sorted(valid.keys()))}")
                            continue
                        if len(tokens) < min_sel or len(tokens) > max_sel:
                            print(f"  {t(f'Select {min_sel}-{max_sel} cards (got {len(tokens)}).', f'需要选 {min_sel}-{max_sel} 张（已选 {len(tokens)} 张）。')}")
                            continue
                        choice_tokens = tokens
                        break

                if skip:
                    state = send({"cmd": "action", "action": "skip_select"})
                else:
                    engine_indices = ",".join(str(valid[tok]["index"]) for tok in choice_tokens)
                    state = send({"cmd": "action", "action": "select_cards",
                                 "args": {"indices": engine_indices}})

            elif dec == "shop":
                show_shop(state)

                if auto:
                    choice = "leave"
                else:
                    choice = get_input(t("Buy [index/r1/p1/rm] or (leave)", "购买 [编号/r1/p1/rm] 或 (leave)离开"), state=state)

                if choice == "leave":
                    state = send({"cmd": "action", "action": "leave_room"})
                elif choice == "rm":
                    state = send({"cmd": "action", "action": "remove_card"})
                elif choice.startswith("r"):
                    state = send({"cmd": "action", "action": "buy_relic",
                                 "args": {"relic_index": int(choice[1:]) - 1}})
                elif choice.startswith("p"):
                    state = send({"cmd": "action", "action": "buy_potion",
                                 "args": {"potion_index": int(choice[1:]) - 1}})
                else:
                    state = send({"cmd": "action", "action": "buy_card",
                                 "args": {"card_index": int(choice) - 1}})

            elif dec == "rest_site":
                show_rest_site(state)
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled")]
                valid = {str(o["index"]+1): o for o in enabled}

                if auto:
                    hp = state.get("player", {}).get("hp", 1)
                    mhp = state.get("player", {}).get("max_hp", 1)
                    heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
                    smith = next((o for o in enabled if o.get("option_id") == "SMITH"), None)
                    pick = (heal if hp < mhp * 0.7 else smith) or (heal or (enabled[0] if enabled else None))
                    choice = str(pick["index"]+1) if pick else "1"
                else:
                    choice = get_input(t("Choose option [index]", "选择 [编号]"), set(valid.keys()), state=state)

                state = send({"cmd": "action", "action": "choose_option",
                             "args": {"option_index": valid[choice]["index"]}})
                if state and state.get("type") == "error":
                    state = send({"cmd": "action", "action": "leave_room"})

            elif dec == "event_choice":
                show_event(state)
                options = state.get("options", [])
                unlocked = [o for o in options if not o.get("is_locked")]
                valid = {str(o["index"]+1): o for o in unlocked}
                valid["leave"] = None

                # Save state before choice to show diff
                old_relics = set(n(r.get("name","?")) for r in state.get("player",{}).get("relics",[]))
                old_deck_cards = [n(cd.get("name","?")) for cd in state.get("player",{}).get("deck",[])]
                old_deck = state.get("player",{}).get("deck_size", 0)
                old_hp = state.get("player",{}).get("hp", 0)
                old_max_hp = state.get("player",{}).get("max_hp", 0)
                old_gold = state.get("player",{}).get("gold", 0)

                if auto:
                    choice = str(unlocked[0]["index"]+1) if unlocked else "leave"
                else:
                    choice = get_input(t("Choose option [index] or (leave)", "选择 [编号] 或 (leave)离开"), set(valid.keys()), state=state)

                if choice == "leave":
                    state = send({"cmd": "action", "action": "leave_room"})
                else:
                    state = send({"cmd": "action", "action": "choose_option",
                                 "args": {"option_index": valid[choice]["index"]}})
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
                        changes.append(f"HP: {old_hp}/{old_max_hp} → {new_hp}/{new_max_hp}")
                    if new_gold != old_gold:
                        diff = new_gold - old_gold
                        changes.append(f"{t('Gold','金')}: {'+' if diff > 0 else ''}{diff}")
                    if changes:
                        print(f"\n  {c(t('Changes:','变化:'), 'yellow')} {'; '.join(changes)}")

            else:
                print(f"  {t('Unknown state:','未知状态:')} {dec}")
                state = send({"cmd": "action", "action": "proceed"})

    finally:
        try:
            proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            proc.stdin.flush()
        except:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            proc.kill()


_CHARACTER_ALIASES = {
    "i": "Ironclad", "ironclad": "Ironclad",
    "s": "Silent",   "silent": "Silent",
    "d": "Defect",   "defect": "Defect",
    "r": "Regent",   "regent": "Regent",
    "n": "Necrobinder", "necrobinder": "Necrobinder",
}

def _resolve_character(value):
    resolved = _CHARACTER_ALIASES.get(value.lower())
    if resolved is None:
        valid = "Ironclad (i), Silent (s), Defect (d), Regent (r), Necrobinder (n)"
        raise argparse.ArgumentTypeError(
            f"Unknown character '{value}'. Valid choices: {valid}. "
            f"For ascension use -a (e.g. sts2 d -a 10) or combined form (e.g. sts2 d10)"
        )
    return resolved

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play Slay the Spire 2 in your terminal")
    parser.add_argument("positional", nargs="*", metavar="ARG",
                       help="Optional: [character] [ascension] e.g. 'd 4' for Defect Ascension 4")
    parser.add_argument("--auto", action="store_true", help="Auto-play with simple AI")
    parser.add_argument("--seed", type=str, default=None, help="Random seed")
    parser.add_argument("-c", "--character", type=_resolve_character, default=None,
                       metavar="CHAR",
                       help="Character: Ironclad (i), Silent (s), Defect (d), Regent (r), Necrobinder (n)")
    parser.add_argument("-a", "--ascension", type=int, default=None,
                       metavar="LEVEL",
                       help="Ascension level (0-20)")
    parser.add_argument("--lang", type=str, default="both",
                       choices=["en", "zh", "both"],
                       help="Display language: en, zh, or both")
    args = parser.parse_args()

    # Apply positional args (character and/or ascension) if not set via flags
    for pos in args.positional:
        if pos.isdigit():
            if args.ascension is None:
                args.ascension = int(pos)
        else:
            # Support combined form like "d10" (character + ascension)
            m = re.match(r'^([a-z]+)(\d+)$', pos)
            if m and args.character is None and args.ascension is None:
                try:
                    args.character = _resolve_character(m.group(1))
                    args.ascension = int(m.group(2))
                except argparse.ArgumentTypeError as e:
                    parser.error(str(e))
            elif args.character is None:
                try:
                    args.character = _resolve_character(pos)
                except argparse.ArgumentTypeError as e:
                    parser.error(str(e))

    args.character = args.character or "Ironclad"
    args.ascension = args.ascension or 0

    import play as _self
    _self.LANG = args.lang

    ensure_setup()
    play(character=args.character, seed=args.seed, auto=args.auto, ascension=args.ascension)
