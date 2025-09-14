"""Mobile app shim.

Requests and Kivy are optional; keep the module import-safe by exposing a
lightweight TradingAppBase. The real Kivy app is only created when the module
is executed as __main__.
"""

class TradingAppBase:
    """Lightweight base class used when Kivy isn't available (import-safe)."""

    def build(self):
        raise RuntimeError("Kivy not available in this environment")


TradingApp = TradingAppBase


if __name__ == "__main__":
    def _run_kivy_app():
        # runtime imports kept inside this function to keep module import-safe
        try:
            import requests
        except Exception:
            requests = None

        try:
            import kivy

            kivy.require("2.0.0")
            from kivy.app import App
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label

            class TradingApp(App):
                def build(self):
                    layout = BoxLayout(orientation="vertical")
                    self.label = Label(text="LeanTrader Mobile")
                    btn_signals = Button(text="Get Signals")
                    btn_signals.bind(on_press=self.get_signals)
                    btn_trade = Button(text="Execute Trade")
                    btn_trade.bind(on_press=self.execute_trade)
                    layout.add_widget(self.label)
                    layout.add_widget(btn_signals)
                    layout.add_widget(btn_trade)
                    return layout

                def get_signals(self, instance):
                    try:
                        resp = requests.get("http://localhost:5000/signals")
                        self.label.text = str(resp.json())
                    except Exception as e:
                        self.label.text = f"Error: {e}"

                def execute_trade(self, instance):
                    data = {"market": "BTC/USDT", "action": "buy", "size": 0.01}
                    try:
                        resp = requests.post("http://localhost:5000/trade", json=data)
                        self.label.text = str(resp.json())
                    except Exception as e:
                        self.label.text = f"Error: {e}"

            TradingApp().run()
        except Exception:
            print("Kivy not available; mobile app cannot run in this environment.")

    _run_kivy_app()

# Allow intentional imports after module-level code when running as __main__
# flake8: noqa: E402
