using System;
using Microsoft.Gaming.XboxGameBar;
using Windows.ApplicationModel;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Navigation;

namespace Keiframe.GameBar
{
    sealed partial class App : Application
    {
        private XboxGameBarWidget _widget;

        public App()
        {
            InitializeComponent();
            Suspending += OnSuspending;
        }

        protected override async void OnActivated(IActivatedEventArgs args)
        {
            XboxGameBarWidgetActivatedEventArgs widgetArgs = null;
            if (args.Kind == ActivationKind.Protocol)
            {
                var protocolArgs = args as IProtocolActivatedEventArgs;
                if (protocolArgs?.Uri?.Scheme == "ms-gamebarwidget")
                {
                    widgetArgs = args as XboxGameBarWidgetActivatedEventArgs;
                }
            }

            if (widgetArgs == null || !widgetArgs.IsLaunchActivation)
            {
                return;
            }

            var rootFrame = new Frame();
            rootFrame.NavigationFailed += OnNavigationFailed;
            Window.Current.Content = rootFrame;

            _widget = new XboxGameBarWidget(
                widgetArgs,
                Window.Current.CoreWindow,
                rootFrame);
            _widget.PinningSupported = true;
            _widget.MinWindowSize = new Size(320, 180);
            _widget.MaxWindowSize = new Size(1600, 900);
            _widget.HorizontalResizeSupported = true;
            _widget.VerticalResizeSupported = true;

            rootFrame.Navigate(typeof(OverlayPage), _widget);
            Window.Current.Closed += WidgetWindowClosed;
            Window.Current.Activate();

            // Keep the widget compact.  A screen-sized transparent widget
            // intercepts every game click until the user enables Game Bar
            // click-through, and its title-bar controls can be pushed outside
            // the usable area on non-16:9 displays.
            await _widget.TryResizeWindowAsync(new Size(520, 360));
            await _widget.CenterWindowAsync();
        }

        protected override void OnLaunched(LaunchActivatedEventArgs args)
        {
            var rootFrame = Window.Current.Content as Frame ?? new Frame();
            rootFrame.NavigationFailed += OnNavigationFailed;
            Window.Current.Content = rootFrame;
            rootFrame.Navigate(typeof(MainPage));
            Window.Current.Activate();
        }

        private void WidgetWindowClosed(
            object sender,
            Windows.UI.Core.CoreWindowEventArgs args)
        {
            _widget = null;
            Window.Current.Closed -= WidgetWindowClosed;
        }

        private static void OnNavigationFailed(
            object sender,
            NavigationFailedEventArgs args)
        {
            throw new InvalidOperationException(
                $"无法打开页面 {args.SourcePageType.FullName}");
        }

        private void OnSuspending(object sender, SuspendingEventArgs args)
        {
            var deferral = args.SuspendingOperation.GetDeferral();
            _widget = null;
            deferral.Complete();
        }
    }
}
