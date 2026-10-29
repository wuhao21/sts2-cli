using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using HarmonyLib;

// Fault injection lives in a separate process; the production protocol has no test hooks.
internal static class Program
{
    private static readonly TaskCompletionSource Gate = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public static void Main(string[] args)
    {
        var root = Path.GetFullPath(args[0]);
        var engineBin = Path.Combine(root, "src", "Sts2Headless", "bin", "Debug", "net9.0");
        AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY", engineBin + Path.DirectorySeparatorChar);
        AssemblyLoadContext.Default.Resolving += (_, name) =>
        {
            foreach (var directory in new[] { engineBin, Path.Combine(root, "lib") })
            {
                var path = Path.Combine(directory, name.Name + ".dll");
                if (File.Exists(path)) return AssemblyLoadContext.Default.LoadFromAssemblyPath(path);
            }
            return null;
        };

        var adapter = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(engineBin, "Sts2Headless.dll"));
        var simType = adapter.GetType("Sts2Headless.RunSimulator", true)!;
        var sim = Activator.CreateInstance(simType)!;
        var router = adapter.GetType("Sts2Headless.Program", true)!
            .GetMethod("HandleCommand", BindingFlags.Static | BindingFlags.NonPublic)!;

        JsonElement Command(object value) => JsonSerializer.SerializeToElement(
            router.Invoke(null, new[] { sim, (object)JsonSerializer.SerializeToElement(value) }));
        JsonElement Action(string action, object? arguments = null) =>
            Command(new { cmd = "action", action, args = arguments ?? new { } });

        Command(new { cmd = "start_run", character = "Ironclad", seed = "mawler-b" });
        Action("leave_room");
        Command(new { cmd = "set_player", hp = args[1] == "death" ? 1 : 65, max_hp = 80,
            relics = Array.Empty<string>(), potions = new[] { "ENERGY_POTION" },
            deck = Enumerable.Repeat("STONE_ARMOR", 5).Concat(Enumerable.Repeat("DEFEND_IRONCLAD", 5)).ToArray() });
        Command(new { cmd = "enter_room", type = "combat", encounter = "MAWLER_NORMAL" });
        var state = Action("end_turn");
        if (args[1] == "death")
        {
            Console.WriteLine(JsonSerializer.Serialize(new { result = state }));
            return;
        }

        state = Action("use_potion", new { potion_index = 0 });
        foreach (var id in new[] { "CARD.STONE_ARMOR", "CARD.DEFEND_IRONCLAD" })
        {
            var card = state.GetProperty("hand").EnumerateArray().First(c => c.GetProperty("id").GetString() == id);
            state = Action("play_card", new { card_index = card.GetProperty("index").GetInt32() });
        }

        // Finish the real setup work, then keep the transition to the next play phase pending.
        var game = AssemblyLoadContext.Default.Assemblies.First(a => a.GetName().Name == "sts2");
        var manager = game.GetType("MegaCrit.Sts2.Core.Combat.CombatManager", true)!;
        var setup = manager.GetMethod("SetupPlayerTurn", BindingFlags.Instance | BindingFlags.NonPublic)!;
        new Harmony("tests.stalled-combat-turn").Patch(setup,
            postfix: new HarmonyMethod(typeof(Program).GetMethod(nameof(StallPlayerTurn))!));

        var timeout = Action("end_turn");
        var retry = Action("end_turn");
        var proceed = Action("proceed");
        var leave = Action("leave_room");
        var play = Action("play_card", new { card_index = 0 });

        var run = simType.GetField("_runState", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(sim)!;
        var players = (System.Collections.IEnumerable)run.GetType().GetProperty("Players")!.GetValue(run)!;
        var enumerator = players.GetEnumerator();
        enumerator.MoveNext();
        var player = enumerator.Current!;
        var creature = player.GetType().GetProperty("Creature")!.GetValue(player)!;
        var actualHp = creature.GetType().GetProperty("CurrentHp")!.GetValue(creature);
        var isDead = creature.GetType().GetProperty("IsDead")!.GetValue(creature);

        Gate.SetResult();
        var isPlayPhase = simType.GetMethod("IsPlayPhase", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var deadline = Environment.TickCount64 + 3000;
        while (!(bool)isPlayPhase.Invoke(sim, null)! && Environment.TickCount64 < deadline)
            Thread.Sleep(5);
        var recovered = Action("end_turn");
        var nextTurn = Action("end_turn");
        Console.WriteLine(JsonSerializer.Serialize(new { timeout, retry, proceed, leave, play,
            actualHp, isDead, recovered, nextTurn }));
    }

    public static void StallPlayerTurn(ref Task __result) => __result = WaitForGate(__result);

    private static async Task WaitForGate(Task original)
    {
        await original.ConfigureAwait(false);
        await Gate.Task.ConfigureAwait(false);
    }
}
