using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Windows.Data.Json;
using Windows.Storage;
using Windows.Storage.Streams;
using Windows.UI.Core;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media.Imaging;
using Windows.UI.Xaml.Navigation;
using Microsoft.Gaming.XboxGameBar;

namespace Keiframe.GameBar
{
    public sealed partial class OverlayPage : Page
    {
        private const string FrameFileName = "overlay.frame";
        private const int MaxHeaderBytes = 64 * 1024;
        private const int MaxImageBytes = 32 * 1024 * 1024;
        private CancellationTokenSource _cancellation;
        private XboxGameBarWidget _widget;
        private DateTimeOffset _lastMailboxWrite = DateTimeOffset.MinValue;
        private DateTimeOffset _lastSuccessfulRead = DateTimeOffset.MinValue;
        private DateTimeOffset _lastDiagnosticWrite = DateTimeOffset.MinValue;
        private bool _sizedToFirstFrame;

        public OverlayPage()
        {
            InitializeComponent();
        }

        protected override void OnNavigatedTo(NavigationEventArgs args)
        {
            base.OnNavigatedTo(args);
            _widget = args.Parameter as XboxGameBarWidget;
            if (_widget != null)
            {
                _widget.RequestedOpacityChanged += RequestedOpacityChanged;
                _widget.ClickThroughEnabledChanged += WidgetStateChanged;
                _widget.GameBarDisplayModeChanged += WidgetStateChanged;
                _widget.PinnedChanged += WidgetStateChanged;
                _widget.VisibleChanged += WidgetStateChanged;
                _widget.WindowBoundsChanged += WidgetStateChanged;
                _widget.WindowStateChanged += WidgetStateChanged;
                ApplyRequestedOpacity();
                UpdateInteractionChrome();
            }
        }

        protected override void OnNavigatedFrom(NavigationEventArgs args)
        {
            if (_widget != null)
            {
                _widget.RequestedOpacityChanged -= RequestedOpacityChanged;
                _widget.ClickThroughEnabledChanged -= WidgetStateChanged;
                _widget.GameBarDisplayModeChanged -= WidgetStateChanged;
                _widget.PinnedChanged -= WidgetStateChanged;
                _widget.VisibleChanged -= WidgetStateChanged;
                _widget.WindowBoundsChanged -= WidgetStateChanged;
                _widget.WindowStateChanged -= WidgetStateChanged;
                _widget = null;
            }
            base.OnNavigatedFrom(args);
        }

        private async void RequestedOpacityChanged(
            XboxGameBarWidget sender,
            object args)
        {
            await Dispatcher.RunAsync(
                CoreDispatcherPriority.Normal,
                ApplyRequestedOpacity);
        }

        private async void WidgetStateChanged(
            XboxGameBarWidget sender,
            object args)
        {
            await Dispatcher.RunAsync(
                CoreDispatcherPriority.Normal,
                () =>
                {
                    UpdateInteractionChrome();
                    _ = WriteWidgetState("widget-state-changed");
                });
        }

        private void UpdateInteractionChrome()
        {
            if (_widget == null)
            {
                InteractionBar.Visibility = Visibility.Visible;
                return;
            }

            var editing = string.Equals(
                _widget.GameBarDisplayMode.ToString(),
                "Foreground",
                StringComparison.OrdinalIgnoreCase);
            InteractionBar.Visibility = editing
                ? Visibility.Visible
                : Visibility.Collapsed;
            ClickThroughWarning.Visibility =
                !editing &&
                _widget.Pinned &&
                !_widget.ClickThroughEnabled
                    ? Visibility.Visible
                    : Visibility.Collapsed;

            if (_widget.ClickThroughEnabled)
            {
                InteractionHint.Text =
                    "已开启点透：关闭 Game Bar 后可正常控制游戏";
            }
            else if (_widget.Pinned)
            {
                InteractionHint.Text =
                    "已固定；点击屏幕顶部工具栏的鼠标图标开启点透";
            }
            else
            {
                InteractionHint.Text =
                    "拖动 Game Bar 标题栏移动；固定后开启点透即可控制游戏";
            }
        }

        private void ApplyRequestedOpacity()
        {
            if (_widget == null)
            {
                Opacity = 1.0;
                return;
            }

            // Game Bar SDK versions have reported RequestedOpacity both as
            // 0..1 and 0..100. Accept both forms so a fully opaque request
            // never turns into an almost invisible 1% widget.
            var requested = _widget.RequestedOpacity;
            if (requested <= 0.0)
            {
                // Some Game Bar builds report 0 during the widget's first
                // activation before the saved opacity has been loaded.
                requested = 1.0;
            }
            if (requested > 1.0)
            {
                requested /= 100.0;
            }
            Opacity = Math.Max(0.0, Math.Min(1.0, requested));
            _ = WriteWidgetState("opacity-applied");
        }

        private void PageLoaded(object sender, RoutedEventArgs args)
        {
            _cancellation = new CancellationTokenSource();
            _ = Task.Run(() => ConnectionLoop(_cancellation.Token));
        }

        private void PageUnloaded(object sender, RoutedEventArgs args)
        {
            _cancellation?.Cancel();
            _cancellation?.Dispose();
            _cancellation = null;
        }

        private async Task ConnectionLoop(CancellationToken cancellationToken)
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    var file = await ApplicationData.Current.LocalFolder.GetFileAsync(
                        FrameFileName);
                    var properties = await file.GetBasicPropertiesAsync();
                    var now = DateTimeOffset.UtcNow;
                    if ((now - properties.DateModified).TotalSeconds > 3.0)
                    {
                        throw new IOException("Keiframe 画面已停止更新");
                    }

                    if (properties.DateModified != _lastMailboxWrite)
                    {
                        byte[] imageBytes;
                        using (var stream = await file.OpenStreamForReadAsync())
                        using (var reader = new BinaryReader(
                            stream,
                            Encoding.UTF8,
                            leaveOpen: true))
                        {
                            var headerSize = reader.ReadInt32();
                            if (headerSize <= 0 || headerSize > MaxHeaderBytes)
                            {
                                throw new InvalidDataException("无效的覆盖层消息头");
                            }

                            var headerBytes = ReadExactly(reader, headerSize);
                            var header = JsonObject.Parse(
                                Encoding.UTF8.GetString(headerBytes));
                            if (header.GetNamedNumber("version", 0) != 1)
                            {
                                throw new InvalidDataException("不支持的覆盖层协议版本");
                            }

                            var imageSize = reader.ReadInt32();
                            if (imageSize <= 0 || imageSize > MaxImageBytes)
                            {
                                throw new InvalidDataException("无效的覆盖层图片");
                            }

                            imageBytes = ReadExactly(reader, imageSize);

                            var frameWidth = (int)header.GetNamedNumber(
                                "width",
                                320);
                            var frameHeight = (int)header.GetNamedNumber(
                                "height",
                                180);
                            await ShowFrame(
                                imageBytes,
                                frameWidth,
                                frameHeight);
                        }

                        _lastMailboxWrite = properties.DateModified;
                    }

                    _lastSuccessfulRead = now;
                    await Task.Delay(100, cancellationToken);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
                catch (Exception error)
                {
                    try
                    {
                        var now = DateTimeOffset.UtcNow;
                        if ((now - _lastDiagnosticWrite).TotalSeconds >= 2.0)
                        {
                            await WriteConnectionError(error);
                            _lastDiagnosticWrite = now;
                        }
                        if ((now - _lastSuccessfulRead).TotalSeconds >= 3.0)
                        {
                            await ShowStatus(
                                "正在等待 Keiframe 与全屏《星际争霸 II》…");
                        }
                        await Task.Delay(200, cancellationToken);
                    }
                    catch (OperationCanceledException)
                    {
                        return;
                    }
                }
            }
        }

        private static byte[] ReadExactly(BinaryReader reader, int count)
        {
            var result = new byte[count];
            var offset = 0;
            while (offset < count)
            {
                var read = reader.Read(result, offset, count - offset);
                if (read <= 0)
                {
                    throw new EndOfStreamException();
                }
                offset += read;
            }
            return result;
        }

        private async Task ShowFrame(
            byte[] pngBytes,
            int frameWidth,
            int frameHeight)
        {
            var completion = new TaskCompletionSource<bool>();
            await Dispatcher.RunAsync(
                CoreDispatcherPriority.Normal,
                async () =>
                {
                    try
                    {
                        using (var stream = new InMemoryRandomAccessStream())
                        {
                            using (var writer = new DataWriter(stream))
                            {
                                writer.WriteBytes(pngBytes);
                                await writer.StoreAsync();
                                await writer.FlushAsync();
                                writer.DetachStream();
                            }

                            stream.Seek(0);
                            var bitmap = new BitmapImage();
                            await bitmap.SetSourceAsync(stream);
                            OverlayImage.Source = bitmap;
                            StatusPanel.Visibility = Visibility.Collapsed;
                        }

                        if (!_sizedToFirstFrame && _widget != null)
                        {
                            _sizedToFirstFrame = true;
                            var targetWidth = Math.Max(
                                320,
                                Math.Min(900, frameWidth));
                            var targetHeight = Math.Max(
                                180,
                                Math.Min(700, frameHeight + 56));
                            await _widget.TryResizeWindowAsync(
                                new Windows.Foundation.Size(
                                    targetWidth,
                                    targetHeight));
                        }

                        completion.TrySetResult(true);
                        await WriteFrameState(pngBytes.Length);
                    }
                    catch (Exception error)
                    {
                        completion.TrySetException(error);
                    }
                });
            await completion.Task;
        }

        private async void ToggleLockClicked(
            object sender,
            RoutedEventArgs args)
        {
            try
            {
                var file = await ApplicationData.Current.LocalFolder.CreateFileAsync(
                    "overlay.command",
                    CreationCollisionOption.ReplaceExisting);
                await FileIO.WriteTextAsync(
                    file,
                    $"toggle_lock\r\n{DateTimeOffset.UtcNow:O}\r\n");
                InteractionHint.Text = "已切换 Keiframe 锁定状态";
            }
            catch (Exception error)
            {
                InteractionHint.Text = $"切换失败：{error.Message}";
            }
        }

        private void CloseWidgetClicked(
            object sender,
            RoutedEventArgs args)
        {
            _widget?.Close();
        }

        private async Task ShowStatus(string message)
        {
            await Dispatcher.RunAsync(
                CoreDispatcherPriority.Normal,
                () =>
                {
                    StatusText.Text = message;
                    StatusPanel.Visibility = Visibility.Visible;
                });
        }

        private async Task WriteFrameState(int imageBytes)
        {
            try
            {
                var file = await ApplicationData.Current.LocalFolder.CreateFileAsync(
                    "frame-state.txt",
                    CreationCollisionOption.ReplaceExisting);
                await FileIO.WriteTextAsync(
                    file,
                    $"ImageBytes={imageBytes}\r\n" +
                    $"UpdatedUtc={DateTimeOffset.UtcNow:O}\r\n");
            }
            catch
            {
            }
        }

        private async Task WriteConnectionError(Exception error)
        {
            try
            {
                var file = await ApplicationData.Current.LocalFolder.CreateFileAsync(
                    "connection-error.txt",
                    CreationCollisionOption.ReplaceExisting);
                await FileIO.WriteTextAsync(
                    file,
                    $"{DateTimeOffset.UtcNow:O}\r\n{error}\r\n");
            }
            catch
            {
            }
        }

        private async Task WriteWidgetState(string reason)
        {
            try
            {
                var text =
                    $"Reason={reason}\r\n" +
                    $"RequestedOpacity={_widget?.RequestedOpacity}\r\n" +
                    $"AppliedOpacity={Opacity}\r\n" +
                    $"Pinned={_widget?.Pinned}\r\n" +
                    $"Visible={_widget?.Visible}\r\n" +
                    $"ClickThroughEnabled={_widget?.ClickThroughEnabled}\r\n" +
                    $"DisplayMode={_widget?.GameBarDisplayMode}\r\n" +
                    $"WindowState={_widget?.WindowState}\r\n" +
                    $"WindowBounds={_widget?.WindowBounds}\r\n" +
                    $"UpdatedUtc={DateTimeOffset.UtcNow:O}\r\n";
                var file = await ApplicationData.Current.LocalFolder.CreateFileAsync(
                    "widget-state.txt",
                    CreationCollisionOption.ReplaceExisting);
                await FileIO.WriteTextAsync(file, text);
            }
            catch
            {
                // Diagnostics must never interfere with the overlay.
            }
        }
    }
}
