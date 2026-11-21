#!/bin/bash
# setup.sh — Copy game DLLs from Steam installation to lib/
#
# Prerequisites:
#   - Slay the Spire 2 installed via Steam
#   - .NET 9+ SDK (ARM64 for Apple Silicon, x64 for Intel/Linux)
#
# Usage:
#   ./setup.sh                    # Auto-detect Steam path
#   ./setup.sh /path/to/game      # Manual game directory

set -eo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve a supplied relative game directory before changing directory.
GAME_DIR="${1:-${STS2_GAME_DIR:-}}"
if [ -n "$GAME_DIR" ]; then
    GAME_DIR="$(cd "$GAME_DIR" && pwd)"
fi
cd "$REPO_DIR"

# ── Locate game directory ──


if [ -z "$GAME_DIR" ]; then
    # Auto-detect based on platform
    case "$(uname -s)" in
        Darwin)
            GAME_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
            if [ ! -d "$GAME_DIR" ]; then
                # Try x86_64
                GAME_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64"
            fi
            ;;
        Linux)
            GAME_DIR="$HOME/.steam/steam/steamapps/common/Slay the Spire 2"
            if [ ! -d "$GAME_DIR" ]; then
                GAME_DIR="$HOME/.local/share/Steam/steamapps/common/Slay the Spire 2"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            GAME_DIR="C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2"
            ;;
    esac
fi

if [ ! -d "$GAME_DIR" ]; then
    echo "❌ Game directory not found: $GAME_DIR"
    echo ""
    echo "Usage: ./setup.sh /path/to/game/data"
    echo ""
    echo "On macOS, this is usually:"
    echo "  ~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
    exit 1
fi

echo "📁 Game directory: $GAME_DIR"

# ── Copy DLLs ──

mkdir -p lib

DLLS=(
    "sts2.dll"
    "SmartFormat.dll"
    "SmartFormat.ZString.dll"
    "Sentry.dll"
    "Sentry.Godot.dll"
    "Steamworks.NET.dll"
    "MonoMod.Backports.dll"
    "MonoMod.ILHelpers.dll"
    "0Harmony.dll"
    "System.IO.Hashing.dll"
)

echo ""
echo "📦 Copying DLLs to lib/..."
for dll in "${DLLS[@]}"; do
    src="$GAME_DIR/$dll"
    if [ -f "$src" ]; then
        cp "$src" "lib/$dll"
        echo "  ✓ $dll"
    else
        echo "  ✗ $dll not found at $src"
        # Try searching subdirectories
        found=$(find "$GAME_DIR" -name "$dll" -print -quit 2>/dev/null)
        if [ -n "$found" ]; then
            cp "$found" "lib/$dll"
            echo "    → found at $found"
        else
            echo "    ⚠ Skipped (may cause build errors)"
        fi
    fi
done

# Back up original sts2.dll
if [ -f "lib/sts2.dll" ]; then
    cp "lib/sts2.dll" "lib/sts2.dll.original"
    echo "  ✓ Backed up sts2.dll.original"
fi

# Refresh text alongside the engine so descriptions match the installed balance.
PCK_PATH="$(find "$GAME_DIR" "$(dirname "$GAME_DIR")" -maxdepth 2 -name '*.pck' -print -quit 2>/dev/null)"
if [ -n "$PCK_PATH" ]; then
    python3 scripts/extract_localization.py "$PCK_PATH"
else
    echo "⚠ No game PCK found; keeping existing localization tables."
fi

# ── Detect .NET SDK ──

DOTNET=""
if [ -x "$HOME/.dotnet-arm64/dotnet" ]; then
    DOTNET="$HOME/.dotnet-arm64/dotnet"
elif command -v dotnet &>/dev/null; then
    DOTNET="dotnet"
fi

if [ -z "$DOTNET" ]; then
    echo ""
    echo "❌ .NET SDK not found."
    echo "   Install .NET 9+ from https://dotnet.microsoft.com/download"
    echo "   Or set DOTNET env var to your dotnet binary path."
    exit 1
fi

echo ""
echo "🔧 .NET SDK: $DOTNET ($($DOTNET --version))"

# ── IL Patch sts2.dll ──

echo ""
echo "🔨 Applying IL patches to sts2.dll..."

# Create a temporary patching project
PATCH_DIR=$(mktemp -d)
cat > "$PATCH_DIR/Patcher.csproj" << 'PROJ'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <RollForward>LatestMajor</RollForward>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Mono.Cecil" Version="0.11.6" />
  </ItemGroup>
</Project>
PROJ

cat > "$PATCH_DIR/Program.cs" << 'CSHARP'
using System;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

var dllPath = args[0];
Console.WriteLine($"Patching {dllPath}...");

var resolver = new DefaultAssemblyResolver();
var libDir = Path.GetDirectoryName(dllPath)!;
resolver.AddSearchDirectory(libDir);
// Also search for GodotSharp.dll in the GodotStubs output (fallback)
var stubsDir = Path.Combine(Path.GetDirectoryName(libDir)!, "src", "GodotStubs", "bin", "Debug", "net9.0");
if (Directory.Exists(stubsDir)) resolver.AddSearchDirectory(stubsDir);
var module = ModuleDefinition.ReadModule(dllPath, new ReaderParameters {
    AssemblyResolver = resolver,
    ReadingMode = ReadingMode.Deferred  // Don't force-resolve all references upfront
});

int patches = 0;

// Patch 1: Task.Yield() — make YieldAwaitable.YieldAwaiter.IsCompleted return true
// This prevents async deadlocks in headless mode
foreach (var type in module.Types)
{
    foreach (var nested in type.NestedTypes)
    {
        foreach (var nested2 in nested.NestedTypes)
        {
            if (nested2.Name.Contains("YieldAwaiter") || nested2.Name == "<>c")
            {
                foreach (var method in nested2.Methods)
                {
                    if (method.Name == "get_IsCompleted" && method.Body != null)
                    {
                        var il = method.Body.GetILProcessor();
                        il.Body.Instructions.Clear();
                        il.Emit(OpCodes.Ldc_I4_1);
                        il.Emit(OpCodes.Ret);
                        patches++;
                        Console.WriteLine($"  Patched {type.Name}.{nested.Name}.{nested2.Name}.IsCompleted");
                    }
                }
            }
        }
    }
}

// Patch 2: WaitUntilQueueIsEmptyOrWaitingOnNonPlayerDrivenAction → return Task.CompletedTask
foreach (var type in module.Types)
{
    foreach (var method in type.Methods)
    {
        if (method.Name == "WaitUntilQueueIsEmptyOrWaitingOnNonPlayerDrivenAction" && method.Body != null)
        {
            var il = method.Body.GetILProcessor();
            il.Body.Instructions.Clear();
            // return Task.CompletedTask
            var taskType = module.ImportReference(typeof(System.Threading.Tasks.Task));
            var completedProp = module.ImportReference(
                typeof(System.Threading.Tasks.Task).GetProperty("CompletedTask")!.GetGetMethod()!);
            il.Emit(OpCodes.Call, completedProp);
            il.Emit(OpCodes.Ret);
            patches++;
            Console.WriteLine($"  Patched {type.Name}.{method.Name} → Task.CompletedTask");
        }
    }
}

// Patch 3: NAudioManager.get_Instance() → return a cached stub NAudioManager when null
// Prevents NullReferenceException in unguarded callers like Crusher.BeforeDeath and
// Rocket.BeforeDeath (Kaiser Crab boss) in headless mode. All NAudioManager methods
// already no-op when TestMode.IsOn / NonInteractiveMode.IsActive.
foreach (var type in module.Types)
{
    if (type.FullName == "MegaCrit.Sts2.Core.Nodes.Audio.NAudioManager")
    {
        var getter = type.Methods.FirstOrDefault(m => m.Name == "get_Instance" && m.Body != null);
        var ctor = type.Methods.FirstOrDefault(m => m.Name == ".ctor" && !m.IsStatic && m.Parameters.Count == 0);
        if (getter != null && ctor != null)
        {
            var field = type.Fields.FirstOrDefault(f => f.Name == "_headlessFallback");
            if (field == null)
            {
                field = new FieldDefinition("_headlessFallback",
                    FieldAttributes.Private | FieldAttributes.Static, type);
                type.Fields.Add(field);
            }
            var il = getter.Body.GetILProcessor();
            getter.Body.Instructions.Clear();
            getter.Body.ExceptionHandlers.Clear();
            getter.Body.Variables.Clear();
            var retInstr = il.Create(OpCodes.Ret);
            il.Emit(OpCodes.Ldsfld, field);
            il.Emit(OpCodes.Dup);
            il.Emit(OpCodes.Brtrue_S, retInstr);
            il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Newobj, ctor);
            il.Emit(OpCodes.Dup);
            il.Emit(OpCodes.Stsfld, field);
            il.Append(retInstr);
            patches++;
            Console.WriteLine($"  Patched {type.Name}.get_Instance → cached stub instance");
        }
    }
}

Console.WriteLine($"Applied {patches} patches");
var outPath = dllPath + ".patched";
module.Write(outPath);
module.Dispose();
File.Delete(dllPath);
File.Move(outPath, dllPath);
Console.WriteLine("Done!");
CSHARP

REPO_DIR="$(pwd)"
cd "$PATCH_DIR"
$DOTNET run -- "$REPO_DIR/lib/sts2.dll" 2>&1
cd "$REPO_DIR"
rm -rf "$PATCH_DIR"

# ── Build ──

echo ""
echo "🏗️ Building..."
$DOTNET build src/Sts2Headless/Sts2Headless.csproj 2>&1 | tail -5

echo ""
echo "✅ Setup complete!"
echo ""
echo "To play:"
echo "  python3 python/play.py"
echo ""
echo "To run batch games:"
echo "  python3 python/play_full_run.py 10"
