namespace Godot;

// CanvasItem
public class CanvasItem : Node
{
    public Color Modulate { get; set; } = Color.White;
    public Color SelfModulate { get; set; } = Color.White;
    public bool Visible { get; set; } = true;
    public virtual void Show() => Visible = true;
    public virtual void Hide() => Visible = false;
    public bool IsVisibleInTree() => Visible;
    public Tween CreateTween() => new Tween();
    public Rect2 GetViewportRect() => new Rect2(Vector2.Zero, new Vector2(1920, 1080));
}

// Control
public class Control : CanvasItem
{
    public enum FocusModeEnum { None, Click, All }
    public enum MouseFilterEnum { Stop, Pass, Ignore }
    public enum LayoutPreset { TopLeft, TopRight, BottomLeft, BottomRight, FullRect }

    public new class MethodName : Node.MethodName { }
    public new class PropertyName : Node.PropertyName { }
    public new class SignalName : Node.SignalName
    {
        public static readonly StringName FocusEntered = "FocusEntered";
        public static readonly StringName FocusExited = "FocusExited";
        public static readonly StringName MouseEntered = "MouseEntered";
        public static readonly StringName MouseExited = "MouseExited";
        public static readonly StringName Resized = "Resized";
    }

    public Vector2 Position { get; set; }
    public Vector2 GlobalPosition { get; set; }
    public Vector2 Size { get; set; }
    public Vector2 CustomMinimumSize { get; set; }
    public float Rotation { get; set; }
    public Vector2 Scale { get; set; } = Vector2.One;
    public Vector2 PivotOffset { get; set; }
    public FocusModeEnum FocusMode { get; set; }
    public MouseFilterEnum MouseFilter { get; set; }
    public string TooltipText { get; set; } = "";

    public Rect2 GetViewportRect() => new Rect2(0, 0, 1920, 1080);
    public void GrabFocus() { }
    public void ReleaseFocus() { }
    public bool HasFocus() => false;
    public Viewport? GetViewport() => null;

    public virtual void _GuiInput(InputEvent @event) { }

    public void Connect(StringName signal, Callable callable) { }
    public void Disconnect(StringName signal, Callable callable) { }
    public void EmitSignal(StringName signal, params Variant[] args) { }
}

// Node2D
public class Node2D : CanvasItem
{
    public new class MethodName : Node.MethodName { }
    public new class PropertyName : Node.PropertyName { }
    public new class SignalName : Node.SignalName { }

    public Vector2 Position { get; set; }
    public Vector2 GlobalPosition { get; set; }
    public float Rotation { get; set; }
    public float RotationDegrees { get; set; }
    public Vector2 Scale { get; set; } = Vector2.One;
    public Transform2D GlobalTransform { get; set; }
    public Transform2D Transform { get; set; }
}

// Resource
public class Resource : GodotObject
{
    public string ResourcePath { get; set; } = "";
    public class MethodName { }
    public class PropertyName { }
    public class SignalName { }
}

// PackedScene
public class PackedScene : Resource
{
    public enum GenEditState { Disabled, Instance, Main }
    public T Instantiate<T>(GenEditState editState = GenEditState.Disabled) where T : Node, new() => new T();
    public Node Instantiate(GenEditState editState = GenEditState.Disabled) => new Node();
}

// Texture types
public class Texture2D : Resource { }
public class CompressedTexture2D : Texture2D { }
public class AtlasTexture : Texture2D
{
    public Rect2 Region { get; set; }
    public Texture2D? Atlas { get; set; }
}
public class ImageTexture : Texture2D { }

// Material types
public class Material : Resource { }
public class ShaderMaterial : Material
{
    public void SetShaderParameter(StringName param, Variant value) { }
    public Variant GetShaderParameter(StringName param) => default;
}
public class Shader : Resource { }

// Curve
public class Curve : Resource
{
    public float Sample(float offset) => 0f;
}

// Tween
public class Tween : GodotObject
{
    public enum EaseType { In, Out, InOut, OutIn }
    public enum TransitionType { Linear, Sine, Quint, Quart, Quad, Expo, Elastic, Cubic, Circ, Bounce, Back, Spring }

    public new class SignalName : GodotObject.SignalName
    {
        public static readonly StringName Finished = "finished";
    }

    public event Action? Finished;

    public PropertyTweener TweenProperty(GodotObject obj, NodePath property, Variant finalVal, double duration) => new();
    public CallbackTweener TweenCallback(Callable callback) => new();
    public MethodTweener TweenMethod(Callable method, Variant from, Variant to, double duration) => new();
    public IntervalTweener TweenInterval(double time) => new();
    public Tween Parallel() => this;
    public Tween SetParallel(bool parallel = true) => this;
    public Tween SetLoops(int loops = 0) => this;
    public Tween SetEase(EaseType ease) => this;
    public Tween SetTrans(TransitionType trans) => this;
    public Tween Chain() => this;
    public bool CustomStep(double delta) { Finished?.Invoke(); return true; }
    public void Play() { Finished?.Invoke(); }
    public void Stop() { }
    public void Pause() { }
    public void Kill() { }
    public bool IsRunning() => false;
    public bool IsValid() => true;
    public Tween BindNode(Node node) => this;
    public Tween SetSpeedScale(float scale) => this;
    public Tween SetProcessMode(ProcessModeEnum mode) => this;
    public enum ProcessModeEnum { Physics, Idle, Always }
}

public class PropertyTweener
{
    public PropertyTweener From(Variant value) => this;
    public PropertyTweener SetEase(Tween.EaseType ease) => this;
    public PropertyTweener SetTrans(Tween.TransitionType trans) => this;
    public PropertyTweener SetDelay(double delay) => this;
    public PropertyTweener AsRelative() => this;
}

public class CallbackTweener
{
    public CallbackTweener SetDelay(double delay) => this;
}

public class MethodTweener
{
    public MethodTweener SetEase(Tween.EaseType ease) => this;
    public MethodTweener SetTrans(Tween.TransitionType trans) => this;
    public MethodTweener SetDelay(double delay) => this;
}

public class IntervalTweener { }

// UI Controls
public class TextureRect : Control
{
    public new class MethodName : Control.MethodName { }
    public new class PropertyName : Control.PropertyName { }
    public new class SignalName : Control.SignalName { }
    public Texture2D? Texture { get; set; }
}

public class ColorRect : Control
{
    public Color Color { get; set; }
}

public class Panel : Control { }
public class PanelContainer : Control { }

public class Container : Control { }
public class BoxContainer : Container { }
public class VBoxContainer : BoxContainer { }
public class HBoxContainer : BoxContainer { }
public class FlowContainer : Container { }
public class HFlowContainer : FlowContainer { }
public class GridContainer : Container
{
    public int Columns { get; set; }
}
public class MarginContainer : Container { }
public class CenterContainer : Container { }
public class ScrollContainer : Container { }
public class SubViewportContainer : Container { }
public class SubViewport : Viewport { }

public class Label : Control
{
    public string Text { get; set; } = "";
}

public class RichTextLabel : Control
{
    public string Text { get; set; } = "";
    public void Clear() { Text = ""; }
    public void AppendText(string text) { Text += text; }
    public void AddText(string text) { Text += text; }
}

public class Button : Control
{
    public new class SignalName : Control.SignalName
    {
        public static readonly StringName Pressed = "Pressed";
    }
    public string Text { get; set; } = "";
    public event Action? Pressed;
}

public class BaseButton : Control
{
    public new class SignalName : Control.SignalName
    {
        public static readonly StringName Pressed = "Pressed";
    }
}

public class CheckBox : Button { }
public class CheckButton : Button { }

public class OptionButton : Button
{
    public int Selected { get; set; }
    public void AddItem(string label, int id = -1) { }
    public void Select(int idx) { Selected = idx; }
}

public class LineEdit : Control
{
    public string Text { get; set; } = "";
    public string PlaceholderText { get; set; } = "";
    public new class SignalName : Control.SignalName
    {
        public static readonly StringName TextChanged = "TextChanged";
        public static readonly StringName TextSubmitted = "TextSubmitted";
    }
}

public class TextEdit : Control
{
    public string Text { get; set; } = "";
}

public class SpinBox : Control
{
    public double Value { get; set; }
}

public class Slider : Control
{
    public double Value { get; set; }
}
public class HSlider : Slider { }
public class VSlider : Slider { }

public class ScrollBar : Control
{
    public double Value { get; set; }
}
public class HScrollBar : ScrollBar { }
public class VScrollBar : ScrollBar { }

public class Separator : Control { }
public class HSeparator : Separator { }
public class VSeparator : Separator { }

public class TabContainer : Container { }

// Timer
public class Timer : Node
{
    public double WaitTime { get; set; } = 1.0;
    public bool OneShot { get; set; }
    public bool Autostart { get; set; }
    public event Action? Timeout;
    public void Start(double timeSec = -1) { Timeout?.Invoke(); }
    public void Stop() { }
}

// Audio
public class AudioStream : Resource { }
public class AudioStreamPlayer : Node
{
    public new class SignalName : Node.SignalName
    {
        public static readonly StringName Finished = "Finished";
    }
    public AudioStream? Stream { get; set; }
    public float VolumeDb { get; set; }
    public void Play(float fromPosition = 0) { }
    public void Stop() { }
}

// Input
public class InputEvent : Resource
{
    public virtual bool IsActionPressed(StringName action, bool allowEcho = false) => false;
    public virtual bool IsActionReleased(StringName action) => false;
    public bool IsPressed() => false;
    public bool IsReleased() => true;
}
public class InputEventKey : InputEvent { }
public class InputEventMouseButton : InputEvent
{
    public Vector2 Position { get; set; }
    public Vector2 GlobalPosition { get; set; }
}
public class InputEventMouseMotion : InputEvent
{
    public Vector2 Position { get; set; }
    public Vector2 Relative { get; set; }
}

// FileAccess
public class FileAccess : GodotObject, IDisposable
{
    public enum ModeFlags { Read, Write, ReadWrite, WriteRead }
    private FileStream? _stream;
    private StreamReader? _reader;
    private StreamWriter? _writer;

    private FileAccess(FileStream stream)
    {
        _stream = stream;
    }

    private static string ResolvePath(string path) => ProjectSettings.GlobalizePath(path);

    public static FileAccess? Open(string path, ModeFlags flags)
    {
        try
        {
            var resolved = ResolvePath(path);
            var dir = Path.GetDirectoryName(resolved);
            if (!string.IsNullOrEmpty(dir) && flags != ModeFlags.Read)
                Directory.CreateDirectory(dir);

            var mode = flags switch
            {
                ModeFlags.Read => FileMode.Open,
                ModeFlags.Write => FileMode.Create,
                ModeFlags.ReadWrite => FileMode.OpenOrCreate,
                ModeFlags.WriteRead => FileMode.Create,
                _ => FileMode.OpenOrCreate,
            };

            var access = flags switch
            {
                ModeFlags.Read => System.IO.FileAccess.Read,
                ModeFlags.Write => System.IO.FileAccess.Write,
                ModeFlags.ReadWrite => System.IO.FileAccess.ReadWrite,
                ModeFlags.WriteRead => System.IO.FileAccess.ReadWrite,
                _ => System.IO.FileAccess.ReadWrite,
            };

            return new FileAccess(new FileStream(resolved, mode, access, FileShare.ReadWrite));
        }
        catch
        {
            return null;
        }
    }

    public static bool FileExists(string path) => File.Exists(ResolvePath(path));

    public ulong GetPosition() => (ulong)(_stream?.Position ?? 0);

    public ulong GetLength() => (ulong)(_stream?.Length ?? 0);

    public void Seek(ulong position)
    {
        if (_stream == null) return;
        _stream.Position = (long)position;
        _reader?.DiscardBufferedData();
    }

    public bool EofReached() => _stream == null || _stream.Position >= _stream.Length;

    public string GetAsText(bool skipCr = false)
    {
        if (_stream == null || !_stream.CanRead) return "";
        _reader ??= new StreamReader(_stream, System.Text.Encoding.UTF8, true, 1024, leaveOpen: true);
        var text = _reader.ReadToEnd();
        return skipCr ? text.Replace("\r", "") : text;
    }

    public string GetLine()
    {
        if (_stream == null || !_stream.CanRead) return "";
        _reader ??= new StreamReader(_stream, System.Text.Encoding.UTF8, true, 1024, leaveOpen: true);
        return _reader.ReadLine() ?? "";
    }

    public void StoreString(string str)
    {
        if (_stream == null || !_stream.CanWrite) return;
        _writer ??= new StreamWriter(_stream, System.Text.Encoding.UTF8, 1024, leaveOpen: true);
        _writer.Write(str);
        _writer.Flush();
    }

    public bool StoreLine(string line)
    {
        StoreString(line + Environment.NewLine);
        return true;
    }

    public void Close()
    {
        _writer?.Flush();
        _writer?.Dispose();
        _writer = null;
        _reader?.Dispose();
        _reader = null;
        _stream?.Dispose();
        _stream = null;
    }

    public void Dispose() => Close();
}

// DirAccess
public class DirAccess : GodotObject, IDisposable
{
    public static bool DirExistsAbsolute(string path) => Directory.Exists(path);
    public static Error MakeDirAbsolute(string path) { try { Directory.CreateDirectory(path); return Error.Ok; } catch { return Error.Failed; } }
    public static Error MakeDirRecursiveAbsolute(string path) { try { Directory.CreateDirectory(path); return Error.Ok; } catch { return Error.Failed; } }
    public Error MakeDirRecursive(string path) { try { Directory.CreateDirectory(Path.Combine(_path, path)); return Error.Ok; } catch { return Error.Failed; } }
    public static DirAccess? Open(string path) => Directory.Exists(path) ? new DirAccess(path) : null;
    private readonly string _path;
    private DirAccess(string path) { _path = path; }
    public DirAccess() { _path = ""; }
    public string[] GetFiles() { try { return Directory.GetFiles(_path).Select(Path.GetFileName).ToArray()!; } catch { return Array.Empty<string>(); } }
    public string[] GetDirectories() { try { return Directory.GetDirectories(_path).Select(Path.GetFileName).ToArray()!; } catch { return Array.Empty<string>(); } }
    public void Dispose() { }
}

// Animation
public class AnimationPlayer : Node
{
    public new class SignalName : Node.SignalName
    {
        public static readonly StringName AnimationFinished = "AnimationFinished";
    }
    public void Play(StringName name = default, double customBlend = -1, float customSpeed = 1f, bool fromEnd = false) { }
    public void Stop(bool keepState = false) { }
}

// Particles
public class GpuParticles2D : Node2D
{
    public bool Emitting { get; set; }
    public Material? ProcessMaterial { get; set; }
}

// Sprite
public class Sprite2D : Node2D
{
    public Texture2D? Texture { get; set; }
}

// CharFXTransform for RichTextEffects
public class CharFXTransform : GodotObject
{
    public Color Color { get; set; } = Color.White;
    public Vector2 Offset { get; set; }
    public Transform2D Transform { get; set; }
    public bool Visible { get; set; } = true;
    public double ElapsedTime { get; set; }
    public uint RelativeIndex { get; set; }
    public Dictionary<Variant, Variant>? Env { get; set; }
}

// RichTextEffect
public class RichTextEffect : Resource
{
    public new class SignalName { }
    public virtual bool _ProcessCustomFX(CharFXTransform charFx) => false;
}

// ResourceFormatLoader
public class ResourceFormatLoader : GodotObject
{
    public class MethodName { }
    public class PropertyName { }
    public class SignalName { }

    public virtual Variant _Load(string path, string originalPath, bool useSubThreads, int cacheMode) => default;
    public virtual string[] _GetRecognizedExtensions() => Array.Empty<string>();
    public virtual bool _HandlesType(StringName type) => false;
    public virtual string _GetResourceType(string path) => "";
    public virtual bool _RecognizePath(string path, StringName type) => false;
    public virtual string[] _GetDependencies(string path, bool addTypes) => Array.Empty<string>();
    public virtual bool _Exists(string path) => false;
}

// Image
public class Image : Resource
{
    public enum Format { Rgba8 }
    public static Image CreateEmpty(int width, int height, bool useMipmaps, Format format) => new();
    public void SetPixel(int x, int y, Color color) { }
}
