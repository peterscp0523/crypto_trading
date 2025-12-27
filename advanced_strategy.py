class AdvancedIndicators:
    @staticmethod
    def calculate_bollinger_bands(prices, period=20, std_dev=2):
        if len(prices) < period:
            return None, None, None
        
        middle = sum(prices[:period]) / period
        variance = sum((p - middle) ** 2 for p in prices[:period]) / period
        std = variance ** 0.5
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, middle, lower
    
    @staticmethod
    def calculate_volume_ma(volumes, period=20):
        if len(volumes) < period:
            return None
        return sum(volumes[:period]) / period