using System.Runtime.CompilerServices;

namespace Godot;

public class GodotObject
{
    public class SignalName { }

    public static bool IsInstanceValid(GodotObject? obj) => obj != null;
    public virtual bool IsQueuedForDeletion() => false;

    // ToSignal - must be on GodotObject (not Node) to match real Godot
    public SignalAwaiter ToSignal(GodotObject source, StringName signal)
    {
        return new SignalAwaiter();
    }

    // Bridge methods overridden in generated code
    protected virtual void SaveGodotObjectData(GodotSerializationInfo info) { }
    protected virtual void RestoreGodotObjectData(GodotSerializationInfo info) { }
    protected virtual bool InvokeGodotClassMethod(in NativeInterop.godot_string_name method, NativeInterop.NativeVariantPtrArgs args, out NativeInterop.godot_variant ret) { ret = default; return false; }
    protected virtual bool HasGodotClassMethod(in NativeInterop.godot_string_name method) => false;
    protected virtual bool SetGodotClassPropertyValue(in NativeInterop.godot_string_name name, in NativeInterop.godot_variant value) => false;
    protected virtual bool GetGodotClassPropertyValue(in NativeInterop.godot_string_name name, out NativeInterop.godot_variant value) { value = default; return false; }
    protected virtual void RaiseGodotClassSignalCallbacks(in NativeInterop.godot_string_name signal, NativeInterop.NativeVariantPtrArgs args) { }
    protected virtual bool HasGodotClassSignal(in NativeInterop.godot_string_name signal) => false;
}

public class Node : GodotObject
{
    public enum InternalMode { Disabled, Front, Back }

    private Node? _parent;
    private readonly List<Node> _children = new();

    public class MethodName
    {
        public static readonly StringName AddChild = "AddChild";
        public static readonly StringName RemoveChild = "RemoveChild";
        public static readonly StringName QueueFree = "QueueFree";
        public static readonly StringName _Ready = "_Ready";
    }

    public class PropertyName { }
    public new class SignalName : GodotObject.SignalName
    {
        public static readonly StringName ProcessFrame = "ProcessFrame";
    }

    public virtual StringName Name { get; set; } = "";

    public Node? GetParent() => _parent;

    public Godot.Collections.Array<Node> GetChildren(bool includeInternal = false)
    {
        return new Godot.Collections.Array<Node>(_children);
    }

    public T? GetNodeOrNull<T>(string path) where T : class => null;
    public T? GetNodeOrNull<T>(NodePath path) where T : class => null;
    public T GetNode<T>(string path) where T : class => default!;
    public T GetNode<T>(NodePath path) where T : class => default!;

    public virtual void AddChild(Node child, bool forceReadableName = false, InternalMode mode = InternalMode.Disabled)
    {
        child._parent = this;
        _children.Add(child);
    }

    public virtual void RemoveChild(Node child)
    {
        child._parent = null;
        _children.Remove(child);
    }

    public void Reparent(Node newParent)
    {
        _parent?.RemoveChild(this);
        newParent.AddChild(this);
    }

    public virtual void QueueFree() { }

    public SceneTree GetTree() => Engine.GetMainLoop() as SceneTree ?? new SceneTree();

    public Tween CreateTween() => new Tween();
    public Viewport GetViewport() => new Viewport();
    public double GetProcessDeltaTime() => 0.016;
    public bool IsAncestorOf(Node node) => false;
    public bool IsInsideTree() => false;
    public int GetChildCount(bool includeInternal = false) => _children.Count;

    public void CallDeferred(StringName method, params Variant[] args) { }

    public virtual void _Ready() { }
    public virtual void _EnterTree() { }
    public virtual void _ExitTree() { }
    public virtual void _Process(double delta) { }
    public virtual void _Notification(int what) { }
    public virtual void _Input(InputEvent @event) { }
    public virtual void _UnhandledInput(InputEvent @event) { }
    public virtual void _UnhandledKeyInput(InputEvent @event) { }
}

public class SceneTree : MainLoop
{
    public new class SignalName : Node.SignalName
    {
        public static new readonly StringName ProcessFrame = "process_frame";
    }

    public SceneTreeTimer CreateTimer(double timeSec, bool processAlways = true, bool processInPhysics = false, bool ignoreTimeScale = false)
    {
        var timer = new SceneTreeTimer();
        // Immediately fire the timeout in headless mode
        timer.FireTimeout();
        return timer;
    }

    public Window Root { get; } = new Window();
}

public class SceneTreeTimer : GodotObject
{
    public event Action? Timeout;

    internal void FireTimeout()
    {
        Timeout?.Invoke();
    }
}

public class MainLoop : GodotObject { }

public static class Engine
{
    private static readonly SceneTree _mainLoop = new();
    public static MainLoop GetMainLoop() => _mainLoop;
    public static bool IsEditorHint() => false;
}

public static class GD
{
    public static void Print(params object[] args) => Console.Error.WriteLine(string.Join("", args));
    public static void Print(string msg) => Console.Error.WriteLine(msg);
    public static void PrintErr(params object[] args) => Console.Error.WriteLine("[ERROR] " + string.Join("", args));
    public static void PrintErr(string msg) => Console.Error.WriteLine("[ERROR] " + msg);
    public static void PushError(params object[] args) => Console.Error.WriteLine("[ERROR] " + string.Join("", args));
    public static void PushError(string msg) => Console.Error.WriteLine("[ERROR] " + msg);
    public static void PushWarning(params object[] args) { }
    public static void PushWarning(string msg) { }
    public static void PrintRich(params object[] args) { }
    public static void PrintRich(string msg) { }
    public static Variant Str(params Variant[] args) => string.Join("", args.Select(a => a.ToString()));
}

public static class OS
{
    public static void ShellOpen(string uri) { }
    public static Error ShellShowInFileManager(string path, bool openFolder = false) => Error.Unavailable;
    public static string GetLocale() => "en";
    public static string GetName() => "headless";
    public static string GetVersion() => "0.0";
    public static string GetExecutablePath() => "";
    public static bool HasFeature(string feature) => false;
    public static bool IsDebugBuild() => false;
    public static string GetDataDir() => ProjectSettings.GlobalizePath("user://");
    public static string GetUserDataDir() => ProjectSettings.GlobalizePath("user://");
    public static string[] GetCmdlineArgs() => Array.Empty<string>();
}

public static class ProjectSettings
{
    public static string GlobalizePath(string path)
    {
        if (string.IsNullOrEmpty(path)) return path;
        if (path.StartsWith("user://", StringComparison.OrdinalIgnoreCase))
            return Path.Combine(Environment.CurrentDirectory, ".godot-user", path.Substring("user://".Length).Replace('/', Path.DirectorySeparatorChar));
        if (path.StartsWith("res://", StringComparison.OrdinalIgnoreCase))
            return Path.Combine(Environment.CurrentDirectory, path.Substring("res://".Length).Replace('/', Path.DirectorySeparatorChar));
        return path;
    }
    public static Variant GetSetting(string name, Variant @default = default) => @default;
    public static bool LoadResourcePack(string path) => false;
}

public static class ResourceLoader
{
    public enum CacheMode { Reuse, Replace, Ignore }
    public static T? Load<T>(string path, string? typeHint = null, CacheMode cacheMode = CacheMode.Reuse) where T : class => null;
    public static bool Exists(string path) => false;
    public static bool Exists(string path, string typeHint) => false;
}

public static class Time
{
    public static ulong GetTicksMsec() => (ulong)Environment.TickCount64;
}

public class Window : Node
{
    public new class SignalName : Node.SignalName
    {
        public static readonly StringName SizeChanged = "SizeChanged";
    }
}

public class Viewport : Node
{
    public new class SignalName : Node.SignalName
    {
        public static readonly StringName GuiFocusChanged = "GuiFocusChanged";
    }

    public Vector2 GetMousePosition() => Vector2.Zero;
    public Rect2 GetVisibleRect() => new Rect2(0, 0, 1920, 1080);
}
