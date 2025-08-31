import kivy
kivy.require('2.0.0')
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
import requests

class TradingApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical')
        self.label = Label(text='LeanTrader Mobile')
        btn_signals = Button(text='Get Signals')
        btn_signals.bind(on_press=self.get_signals)
        btn_trade = Button(text='Execute Trade')
        btn_trade.bind(on_press=self.execute_trade)
        layout.add_widget(self.label)
        layout.add_widget(btn_signals)
        layout.add_widget(btn_trade)
        return layout

    def get_signals(self, instance):
        try:
            resp = requests.get('http://localhost:5000/signals')
            self.label.text = str(resp.json())
        except Exception as e:
            self.label.text = f'Error: {e}'

    def execute_trade(self, instance):
        # Example trade data
        data = {'market': 'BTC/USDT', 'action': 'buy', 'size': 0.01}
        try:
            resp = requests.post('http://localhost:5000/trade', json=data)
            self.label.text = str(resp.json())
        except Exception as e:
            self.label.text = f'Error: {e}'

if __name__ == '__main__':
    TradingApp().run()
