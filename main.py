import asyncio
import pandas as pd
import pandas_ta as ta
from ib_insync import IB, Stock, util
import nest_asyncio
nest_asyncio.apply()

class TradeSignalEvaluator:
    def __init__(self, host='127.0.0.1', port=7496, client_id=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id

    async def connect(self):
        """Connects to the Interactive Brokers TWS or Gateway."""
        try:
            await self.ib.connectAsync(self.host, self.port, self.client_id)
            print(f"Connected to IB Gateway/TWS at {self.host}:{self.port}")
        except Exception as e:
            print(f"Could not connect to IB: {e}")
            # Exit if connection fails, as it's a prerequisite
            exit()

    async def disconnect(self):
        """Disconnects from the Interactive Brokers TWS or Gateway."""
        if self.ib.isConnected():
            self.ib.disconnect()
            print("Disconnected from IB.")

    async def get_historical_data(self, symbol: str, timeframe: str = '5 mins', duration: str = '1 D'):
        """
        Fetches historical data for a given symbol.
        timeframe examples: '1 min', '5 mins', '1 hour', '1 day'
        duration examples: '1 D', '1 W', '1 M', '1 Y'
        """
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)

        print(f"Fetching {duration} of {timeframe} historical data for {symbol}...")
        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting=timeframe,
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        if not bars:
            print(f"No historical data found for {symbol} with timeframe {timeframe} and duration {duration}.")
            return pd.DataFrame()

        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        print(f"Successfully fetched {len(df)} bars for {symbol}.")
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        """Calculates various technical indicators."""
        if df.empty:
            return {}

        indicators = {}
        # Ensure original columns are lowercase before calculating indicators
        df.columns = [col.lower() for col in df.columns]

        # Calculate all technical indicators first
        df.ta.ema(length=13, append=True)
        df.ta.rsi(append=True)
        df.ta.macd(append=True)
        if all(col in df.columns for col in ['high', 'low', 'close', 'volume']):
            df.ta.vwap(append=True)

        # After all indicators are calculated, convert all column names (including new ones) to lowercase
        df.columns = [col.lower() for col in df.columns]

        last_close = df['close'].iloc[-1]

        # 1. 13 EMA
        last_ema13 = df['ema_13'].iloc[-1]
        indicators['ema_13'] = bool(last_close > last_ema13)

        # 2. VWAP
        if 'vwap_d' in df.columns:
            last_vwap = df['vwap_d'].iloc[-1]
            indicators['vwap'] = bool(last_close > last_vwap)
        else:
            indicators['vwap'] = False

        # 3. RSI
        # The default rsi length is 14, so the column is rsi_14
        last_rsi = df['rsi_14'].iloc[-1]
        indicators['rsi'] = bool(last_rsi > 50) # Bullish bias

        # 4. MACD
        # The default macd histogram column is macdh_12_26_9
        last_macd_hist = df['macdh_12_26_9'].iloc[-1]
        indicators['macd'] = bool(last_macd_hist > 0)

        # 5. Volume (simple check: last volume > average volume)
        if 'volume' in df.columns and len(df) > 10: # Need enough data for average
            avg_volume = df['volume'].iloc[:-1].mean()
            last_volume = df['volume'].iloc[-1]
            indicators['volume'] = bool(last_volume > avg_volume)
        else:
            indicators['volume'] = False

        # 6. Break of Structure (BoS) - Placeholder, requires more complex logic
        if len(df) > 5:
            indicators['break_of_structure'] = bool(df['close'].iloc[-1] > df['close'].iloc[-5:-1].max())
        else:
            indicators['break_of_structure'] = False

        return indicators

    def make_recommendation(self, indicators: dict):
        """Applies decision logic based on indicator signals."""
        if not indicators:
            return {"recommendation": "Hold / Wait", "positive_signals": 0}

        positive_signals = sum(1 for signal in indicators.values() if signal)
        total_indicators = len(indicators)

        recommendation = "Hold / Wait"
        if positive_signals >= 5:
            recommendation = "Strong Buy"
        elif positive_signals >= 3:
            recommendation = "Cautious Buy"
        elif positive_signals == 0:
            recommendation = "Do Not Enter"

        return {
            "positive_signals": positive_signals,
            "total_indicators": total_indicators,
            "recommendation": recommendation
        }

    async def evaluate_symbol(self, symbol: str, timeframe: str = '5 mins', duration: str = '1 D'):
        """Main function to evaluate a single stock symbol."""
        await self.connect()
        df = await self.get_historical_data(symbol, timeframe, duration)
        await self.disconnect()

        if df.empty:
            return {
                "symbol": symbol,
                "positive_signals": 0,
                "total_indicators": 0,
                "indicators": {},
                "recommendation": "Could not retrieve data."
            }

        indicators = self.calculate_indicators(df)
        recommendation_data = self.make_recommendation(indicators)

        result = {
            "symbol": symbol,
            "positive_signals": recommendation_data["positive_signals"],
            "total_indicators": recommendation_data["total_indicators"],
            "indicators": indicators,
            "recommendation": recommendation_data["recommendation"]
        }
        return result

async def main():
    evaluator = TradeSignalEvaluator()
    symbol = input("Enter stock symbol (e.g., TSLA): ").upper()
    if not symbol:
        print("No symbol entered. Exiting.")
        return

    # You can customize timeframe and duration here if needed
    result = await evaluator.evaluate_symbol(symbol, timeframe='5 mins', duration='1 D')
    print("\n--- Evaluation Result ---")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())