class TechnicalIndicators:
    @staticmethod
    def calculate_rsi(prices, period=14):
        if len(prices) < period + 1:
            return None
        
        deltas = []
        for i in range(len(prices) - 1):
            deltas.append(prices[i] - prices[i + 1])
        
        gains = [d if d > 0 else 0 for d in deltas[:period]]
        losses = [-d if d < 0 else 0 for d in deltas[:period]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_ma(prices, period=20):
        if len(prices) < period:
            return None
        return sum(prices[:period]) / period