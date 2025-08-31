from flask import Flask, jsonify, request
from ultra_core import UltraCore
from router import ExchangeRouter

app = Flask(__name__)
core = UltraCore(ExchangeRouter(), None)

@app.route('/signals', methods=['GET'])
def get_signals():
    signals = core.scout_opportunities(core.scan_markets())
    return jsonify(signals)

@app.route('/trade', methods=['POST'])
def execute_trade():
    data = request.json
    plans = core.plan_trades([data])
    results = core.enter_trades(plans)
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
