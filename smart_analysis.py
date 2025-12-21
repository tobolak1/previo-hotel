#!/usr/bin/env python3
"""
Smart Analysis System V1
- Backtesting engine
- ML predictions
- Fundamental analysis
- Sentiment analysis
- Combined scoring
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# SUPABASE CONFIG
# ============================================================================

SUPABASE_URL = "https://kchbzmncwdidjzxnegck.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtjaGJ6bW5jd2RpZGp6eG5lZ2NrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwNDI0OTcsImV4cCI6MjA4MDYxODQ5N30._ux0OeOtSZASFsm3brmBRZivC56BQ_iGylwCmwk-ZDU"


def supabase_get(table: str, params: dict = None) -> list:
    """GET from Supabase"""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    return resp.json() if resp.status_code == 200 else []


# ============================================================================
# 1. BACKTESTING ENGINE
# ============================================================================

class BacktestEngine:
    """
    Backtests trading strategies on historical data.
    Tests: If we followed the signals, how would we perform?
    """

    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.results = {}

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for backtesting"""
        # SMA
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        return df

    def generate_signals(self, df: pd.DataFrame, strategy: str = 'combined') -> pd.DataFrame:
        """Generate buy/sell signals based on strategy"""
        df['signal'] = 0  # 0 = hold, 1 = buy, -1 = sell

        if strategy == 'rsi':
            # RSI strategy: Buy when oversold, sell when overbought
            df.loc[df['rsi'] < 30, 'signal'] = 1
            df.loc[df['rsi'] > 70, 'signal'] = -1

        elif strategy == 'macd':
            # MACD crossover strategy
            df['macd_cross'] = np.where(df['macd'] > df['macd_signal'], 1, -1)
            df['signal'] = df['macd_cross'].diff()
            df['signal'] = df['signal'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

        elif strategy == 'sma_cross':
            # Golden/Death cross (SMA50 vs SMA200)
            df['sma_cross'] = np.where(df['sma_50'] > df['sma_200'], 1, -1)
            df['signal'] = df['sma_cross'].diff()
            df['signal'] = df['signal'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

        elif strategy == 'combined':
            # Combined strategy - score based
            score = pd.Series(0, index=df.index)

            # RSI component
            score += np.where(df['rsi'] < 30, 25, 0)
            score += np.where(df['rsi'] > 70, -15, 0)
            score += np.where((df['rsi'] >= 30) & (df['rsi'] < 40), 10, 0)

            # Trend component
            score += np.where(df['close'] > df['sma_50'], 15, -15)
            score += np.where(df['close'] > df['sma_200'], 15, -15)

            # MACD component
            score += np.where(df['macd'] > df['macd_signal'], 10, -10)

            # Generate signals from score
            df['score'] = score
            df.loc[score >= 40, 'signal'] = 1  # Strong buy
            df.loc[score <= -30, 'signal'] = -1  # Strong sell

        return df

    def run_backtest(self, df: pd.DataFrame, strategy: str = 'combined') -> Dict:
        """Run backtest on historical data"""
        df = self.calculate_indicators(df.copy())
        df = self.generate_signals(df, strategy)

        # Remove NaN rows (from indicator calculations)
        df = df.dropna()

        if len(df) < 50:
            return {'error': 'Not enough data for backtesting'}

        # Simulate trading
        capital = self.initial_capital
        position = 0  # Number of shares held
        trades = []
        equity_curve = []

        for i, row in df.iterrows():
            current_value = capital + (position * row['close'])
            equity_curve.append({'date': i, 'equity': current_value})

            if row['signal'] == 1 and position == 0:
                # Buy signal - invest all capital
                shares = capital / row['close']
                position = shares
                capital = 0
                trades.append({
                    'date': i, 'type': 'BUY', 'price': row['close'],
                    'shares': shares, 'value': shares * row['close']
                })

            elif row['signal'] == -1 and position > 0:
                # Sell signal - sell all
                capital = position * row['close']
                trades.append({
                    'date': i, 'type': 'SELL', 'price': row['close'],
                    'shares': position, 'value': capital
                })
                position = 0

        # Final value
        final_value = capital + (position * df.iloc[-1]['close'])

        # Calculate metrics
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # Buy & Hold comparison
        buy_hold_return = ((df.iloc[-1]['close'] - df.iloc[0]['close']) / df.iloc[0]['close']) * 100

        # Calculate max drawdown
        equity_df = pd.DataFrame(equity_curve)
        if len(equity_df) > 0:
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0

        # Win rate
        profitable_trades = 0
        total_trades = len([t for t in trades if t['type'] == 'SELL'])

        for i in range(0, len(trades) - 1, 2):
            if i + 1 < len(trades):
                buy_price = trades[i]['price']
                sell_price = trades[i + 1]['price']
                if sell_price > buy_price:
                    profitable_trades += 1

        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

        return {
            'strategy': strategy,
            'initial_capital': self.initial_capital,
            'final_value': round(final_value, 2),
            'total_return_pct': round(total_return, 2),
            'buy_hold_return_pct': round(buy_hold_return, 2),
            'outperformance': round(total_return - buy_hold_return, 2),
            'total_trades': len(trades),
            'win_rate_pct': round(win_rate, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'trades': trades[-10:],  # Last 10 trades
            'period_days': len(df)
        }

    def backtest_symbol(self, symbol: str, strategy: str = 'combined') -> Dict:
        """Backtest a single symbol using data from Supabase"""
        # Get historical prices
        prices = supabase_get('finance_prices', {
            'select': 'date,open,high,low,close,volume',
            'symbol': f'eq.{symbol}',
            'order': 'date.asc'
        })

        if not prices or len(prices) < 250:
            return {'symbol': symbol, 'error': 'Insufficient data'}

        df = pd.DataFrame(prices)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)

        result = self.run_backtest(df, strategy)
        result['symbol'] = symbol

        return result


# ============================================================================
# 2. ML PREDICTION MODEL
# ============================================================================

class MLPredictor:
    """
    Simple ML model for price prediction.
    Uses historical patterns to predict future movement.
    """

    def __init__(self):
        self.model_weights = {}

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for ML"""
        # Price features
        df['return_1d'] = df['close'].pct_change(1)
        df['return_5d'] = df['close'].pct_change(5)
        df['return_20d'] = df['close'].pct_change(20)

        # Volatility
        df['volatility_20d'] = df['return_1d'].rolling(20).std()

        # Volume features
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # Technical indicators (normalized)
        df['rsi_norm'] = df['rsi'] / 100 if 'rsi' in df.columns else 0.5
        df['price_vs_sma50'] = (df['close'] / df['sma_50'] - 1) if 'sma_50' in df.columns else 0
        df['price_vs_sma200'] = (df['close'] / df['sma_200'] - 1) if 'sma_200' in df.columns else 0

        # Target: Next 5-day return (what we want to predict)
        df['target'] = df['close'].shift(-5) / df['close'] - 1

        return df

    def train_simple_model(self, df: pd.DataFrame) -> Dict:
        """
        Train a simple pattern-based model.
        This finds which indicator combinations historically led to gains.
        """
        df = df.dropna()

        if len(df) < 100:
            return {'error': 'Insufficient data for training'}

        # Split data
        train_size = int(len(df) * 0.8)
        train = df.iloc[:train_size]
        test = df.iloc[train_size:]

        # Find patterns that worked
        patterns = {
            'rsi_oversold': train[train['rsi'] < 30]['target'].mean() if 'rsi' in train.columns else 0,
            'rsi_overbought': train[train['rsi'] > 70]['target'].mean() if 'rsi' in train.columns else 0,
            'above_sma50': train[train['close'] > train['sma_50']]['target'].mean() if 'sma_50' in train.columns else 0,
            'below_sma50': train[train['close'] < train['sma_50']]['target'].mean() if 'sma_50' in train.columns else 0,
            'high_volume': train[train['volume_ratio'] > 1.5]['target'].mean() if 'volume_ratio' in train.columns else 0,
            'positive_momentum': train[train['return_5d'] > 0.02]['target'].mean(),
            'negative_momentum': train[train['return_5d'] < -0.02]['target'].mean(),
        }

        # Clean NaN
        patterns = {k: (v if pd.notna(v) else 0) for k, v in patterns.items()}

        self.model_weights = patterns

        # Test accuracy
        test_predictions = []
        test_actuals = []

        for i, row in test.iterrows():
            pred_score = 0
            if 'rsi' in test.columns:
                if row['rsi'] < 30:
                    pred_score += patterns['rsi_oversold'] * 100
                elif row['rsi'] > 70:
                    pred_score += patterns['rsi_overbought'] * 100

            if 'sma_50' in test.columns and pd.notna(row['sma_50']):
                if row['close'] > row['sma_50']:
                    pred_score += patterns['above_sma50'] * 50
                else:
                    pred_score += patterns['below_sma50'] * 50

            if row['return_5d'] > 0.02:
                pred_score += patterns['positive_momentum'] * 50
            elif row['return_5d'] < -0.02:
                pred_score += patterns['negative_momentum'] * 50

            predicted_direction = 1 if pred_score > 0 else -1
            actual_direction = 1 if row['target'] > 0 else -1

            test_predictions.append(predicted_direction)
            test_actuals.append(actual_direction)

        # Calculate accuracy
        correct = sum(1 for p, a in zip(test_predictions, test_actuals) if p == a)
        accuracy = correct / len(test_predictions) * 100 if test_predictions else 0

        return {
            'patterns': patterns,
            'accuracy_pct': round(accuracy, 2),
            'train_samples': len(train),
            'test_samples': len(test),
            'insight': self._generate_insight(patterns)
        }

    def _generate_insight(self, patterns: Dict) -> str:
        """Generate human-readable insight from patterns"""
        insights = []

        if patterns.get('rsi_oversold', 0) > 0.01:
            insights.append(f"RSI < 30 historically led to +{patterns['rsi_oversold']*100:.1f}% in 5 days")
        if patterns.get('rsi_overbought', 0) < -0.01:
            insights.append(f"RSI > 70 historically led to {patterns['rsi_overbought']*100:.1f}% in 5 days")
        if patterns.get('above_sma50', 0) > patterns.get('below_sma50', 0):
            insights.append("Stocks above SMA50 performed better than those below")
        if patterns.get('positive_momentum', 0) > 0:
            insights.append("Positive momentum tends to continue")

        return " | ".join(insights) if insights else "No clear patterns found"

    def predict(self, current_data: Dict) -> Dict:
        """Make prediction for current data"""
        if not self.model_weights:
            return {'error': 'Model not trained'}

        score = 0
        factors = []

        rsi = current_data.get('rsi')
        if rsi:
            if rsi < 30:
                weight = self.model_weights.get('rsi_oversold', 0)
                score += weight * 100
                factors.append(f"RSI oversold: {'+' if weight > 0 else ''}{weight*100:.1f}%")
            elif rsi > 70:
                weight = self.model_weights.get('rsi_overbought', 0)
                score += weight * 100
                factors.append(f"RSI overbought: {'+' if weight > 0 else ''}{weight*100:.1f}%")

        price = current_data.get('price')
        sma50 = current_data.get('sma_50')
        if price and sma50:
            if price > sma50:
                weight = self.model_weights.get('above_sma50', 0)
                score += weight * 50
                factors.append(f"Above SMA50: {'+' if weight > 0 else ''}{weight*100:.1f}%")
            else:
                weight = self.model_weights.get('below_sma50', 0)
                score += weight * 50
                factors.append(f"Below SMA50: {'+' if weight > 0 else ''}{weight*100:.1f}%")

        return {
            'ml_score': round(score, 2),
            'predicted_direction': 'UP' if score > 0 else 'DOWN' if score < 0 else 'NEUTRAL',
            'confidence': min(abs(score) / 5, 100),  # Normalize to 0-100
            'factors': factors
        }


# ============================================================================
# 3. FUNDAMENTAL ANALYSIS
# ============================================================================

class FundamentalAnalyzer:
    """
    Analyzes fundamental data (P/E, growth, etc.)
    Compares to sector averages.
    """

    # Sector average P/E ratios (approximate)
    SECTOR_PE_AVERAGES = {
        'Technology': 28,
        'Financial Services': 12,
        'Healthcare': 22,
        'Consumer Cyclical': 20,
        'Consumer Defensive': 24,
        'Communication Services': 18,
        'Industrials': 20,
        'Energy': 12,
        'Utilities': 18,
        'Real Estate': 35,
        'Basic Materials': 15,
    }

    def analyze(self, stock_data: Dict, fundamentals: Dict) -> Dict:
        """Analyze fundamentals and generate score"""
        score = 0
        factors = []

        symbol = stock_data.get('symbol', '')
        sector = stock_data.get('sector', 'Unknown')

        # P/E Analysis
        pe = fundamentals.get('pe_ratio')
        if pe and pe > 0:
            sector_avg = self.SECTOR_PE_AVERAGES.get(sector, 20)

            if pe < sector_avg * 0.7:
                score += 20
                factors.append(f"P/E {pe:.1f} je pod průměrem sektoru ({sector_avg}) - podhodnocená")
            elif pe < sector_avg:
                score += 10
                factors.append(f"P/E {pe:.1f} mírně pod průměrem sektoru ({sector_avg})")
            elif pe > sector_avg * 1.5:
                score -= 15
                factors.append(f"P/E {pe:.1f} vysoko nad průměrem sektoru ({sector_avg}) - drahá")
            elif pe > sector_avg:
                score -= 5
                factors.append(f"P/E {pe:.1f} nad průměrem sektoru ({sector_avg})")

        # Profit Margin
        margin = fundamentals.get('profit_margin')
        if margin:
            if margin > 0.20:
                score += 15
                factors.append(f"Vysoká zisková marže {margin*100:.1f}%")
            elif margin > 0.10:
                score += 5
                factors.append(f"Dobrá zisková marže {margin*100:.1f}%")
            elif margin < 0:
                score -= 20
                factors.append(f"Záporná marže {margin*100:.1f}% - ztrátová")

        # Revenue Growth
        growth = fundamentals.get('revenue_growth')
        if growth:
            if growth > 0.20:
                score += 15
                factors.append(f"Silný růst tržeb +{growth*100:.1f}%")
            elif growth > 0.05:
                score += 5
                factors.append(f"Solidní růst tržeb +{growth*100:.1f}%")
            elif growth < 0:
                score -= 10
                factors.append(f"Klesající tržby {growth*100:.1f}%")

        # ROE (Return on Equity)
        roe = fundamentals.get('return_on_equity')
        if roe:
            if roe > 0.20:
                score += 10
                factors.append(f"Výborné ROE {roe*100:.1f}%")
            elif roe > 0.10:
                score += 5
                factors.append(f"Dobré ROE {roe*100:.1f}%")
            elif roe < 0:
                score -= 10
                factors.append(f"Záporné ROE {roe*100:.1f}%")

        # Debt to Equity
        debt = fundamentals.get('debt_to_equity')
        if debt:
            if debt < 0.5:
                score += 10
                factors.append(f"Nízký dluh (D/E: {debt:.2f})")
            elif debt > 2:
                score -= 15
                factors.append(f"Vysoký dluh (D/E: {debt:.2f}) - riziko")

        # Dividend
        div_yield = fundamentals.get('dividend_yield')
        if div_yield and div_yield > 0.02:
            score += 5
            factors.append(f"Dividenda {div_yield*100:.1f}%")

        # 52-week position
        high_52 = fundamentals.get('fifty_two_week_high')
        low_52 = fundamentals.get('fifty_two_week_low')
        current_price = stock_data.get('price')

        if high_52 and low_52 and current_price:
            position = (current_price - low_52) / (high_52 - low_52) if (high_52 - low_52) > 0 else 0.5
            if position < 0.3:
                score += 10
                factors.append(f"Blízko 52-týdenního minima ({position*100:.0f}% range)")
            elif position > 0.9:
                score -= 5
                factors.append(f"Blízko 52-týdenního maxima ({position*100:.0f}% range)")

        return {
            'fundamental_score': max(-50, min(50, score)),
            'factors': factors,
            'sector': sector,
            'pe_ratio': pe,
            'profit_margin': margin,
            'revenue_growth': growth
        }


# ============================================================================
# 4. SENTIMENT ANALYSIS
# ============================================================================

class SentimentAnalyzer:
    """
    Analyzes market sentiment from various sources.
    Note: Full implementation would need API keys for news/social media.
    """

    def __init__(self):
        # Simple keyword-based sentiment (for demo)
        self.positive_keywords = [
            'beat', 'surge', 'rally', 'growth', 'profit', 'upgrade',
            'bullish', 'record', 'strong', 'buy', 'outperform'
        ]
        self.negative_keywords = [
            'miss', 'fall', 'drop', 'loss', 'downgrade', 'bearish',
            'weak', 'sell', 'underperform', 'decline', 'crash'
        ]

    def analyze_text(self, text: str) -> Dict:
        """Simple sentiment analysis on text"""
        text_lower = text.lower()

        positive_count = sum(1 for word in self.positive_keywords if word in text_lower)
        negative_count = sum(1 for word in self.negative_keywords if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return {'sentiment': 'neutral', 'score': 0, 'confidence': 0}

        score = (positive_count - negative_count) / total * 100

        return {
            'sentiment': 'positive' if score > 20 else 'negative' if score < -20 else 'neutral',
            'score': round(score, 2),
            'confidence': min(total * 10, 100),
            'positive_signals': positive_count,
            'negative_signals': negative_count
        }

    def get_market_sentiment(self) -> Dict:
        """
        Get overall market sentiment.
        In production, this would fetch from news APIs, Twitter, Reddit, etc.
        """
        # Placeholder - would need API integration
        return {
            'market_sentiment': 'neutral',
            'vix_level': 'normal',  # Would fetch actual VIX
            'note': 'Full sentiment analysis requires news API integration'
        }


# ============================================================================
# 5. COMBINED SMART SCORE
# ============================================================================

class SmartScoreCalculator:
    """
    Combines all analysis methods into one smart score.
    """

    def __init__(self):
        self.backtest = BacktestEngine()
        self.ml = MLPredictor()
        self.fundamental = FundamentalAnalyzer()
        self.sentiment = SentimentAnalyzer()

        # Weights for each component
        self.weights = {
            'technical': 0.30,      # Current technical indicators
            'fundamental': 0.25,    # P/E, margins, growth
            'ml_prediction': 0.25,  # ML model prediction
            'backtest': 0.20,       # Historical strategy performance
        }

    def calculate_smart_score(
        self,
        symbol: str,
        price_data: Dict,
        indicator_data: Dict,
        fundamental_data: Dict,
        stock_info: Dict
    ) -> Dict:
        """Calculate comprehensive smart score"""

        scores = {}
        all_factors = []

        # 1. Technical Score (existing algorithm)
        technical_score = self._calculate_technical_score(price_data, indicator_data)
        scores['technical'] = technical_score['score']
        all_factors.extend(technical_score['factors'])

        # 2. Fundamental Score
        if fundamental_data:
            fund_result = self.fundamental.analyze(
                {'symbol': symbol, 'sector': stock_info.get('sector'), 'price': price_data.get('price')},
                fundamental_data
            )
            scores['fundamental'] = fund_result['fundamental_score']
            all_factors.extend(fund_result['factors'])
        else:
            scores['fundamental'] = 0

        # 3. ML Prediction Score
        ml_result = self.ml.predict({
            'rsi': indicator_data.get('rsi_14'),
            'price': price_data.get('price'),
            'sma_50': indicator_data.get('sma_50')
        })
        scores['ml_prediction'] = ml_result.get('ml_score', 0)
        if ml_result.get('factors'):
            all_factors.extend(ml_result['factors'])

        # 4. Backtest Score (simplified - based on strategy performance)
        # Would be calculated from historical backtest results
        scores['backtest'] = 0  # Placeholder - calculated separately

        # Calculate weighted final score
        final_score = sum(
            scores[k] * self.weights[k]
            for k in self.weights.keys()
        )

        # Normalize to -100 to +100
        final_score = max(-100, min(100, final_score))

        # Generate recommendation
        if final_score >= 50:
            recommendation = 'SILNÝ NÁKUP'
            confidence = 'vysoká'
        elif final_score >= 25:
            recommendation = 'KOUPIT'
            confidence = 'střední'
        elif final_score >= 10:
            recommendation = 'MÍRNÝ NÁKUP'
            confidence = 'nízká'
        elif final_score <= -50:
            recommendation = 'SILNÝ PRODEJ'
            confidence = 'vysoká'
        elif final_score <= -25:
            recommendation = 'PRODAT'
            confidence = 'střední'
        elif final_score <= -10:
            recommendation = 'MÍRNÝ PRODEJ'
            confidence = 'nízká'
        else:
            recommendation = 'DRŽET'
            confidence = 'neutrální'

        return {
            'symbol': symbol,
            'smart_score': round(final_score, 1),
            'recommendation': recommendation,
            'confidence': confidence,
            'component_scores': {
                'technical': round(scores['technical'], 1),
                'fundamental': round(scores['fundamental'], 1),
                'ml_prediction': round(scores['ml_prediction'], 1),
            },
            'factors': all_factors,
            'weights_used': self.weights
        }

    def _calculate_technical_score(self, price_data: Dict, indicator_data: Dict) -> Dict:
        """Calculate technical score (same as existing algorithm)"""
        score = 0
        factors = []

        price = price_data.get('price', 0)
        rsi = indicator_data.get('rsi_14')
        sma20 = indicator_data.get('sma_20')
        sma50 = indicator_data.get('sma_50')
        sma200 = indicator_data.get('sma_200')
        macd = indicator_data.get('macd')
        macd_signal = indicator_data.get('macd_signal')

        # RSI
        if rsi:
            if rsi < 30:
                score += 25
                factors.append(f'RSI={rsi:.1f} (přeprodaná) +25')
            elif rsi < 40:
                score += 10
                factors.append(f'RSI={rsi:.1f} (nízké) +10')
            elif rsi > 70:
                score -= 15
                factors.append(f'RSI={rsi:.1f} (překoupená) -15')
            elif rsi > 60:
                score += 5
                factors.append(f'RSI={rsi:.1f} (silné) +5')

        # Trend
        if price and sma20 and sma50:
            if price > sma20 > sma50:
                score += 20
                factors.append('Uptrend (cena > SMA20 > SMA50) +20')
            elif price < sma20 < sma50:
                score -= 20
                factors.append('Downtrend (cena < SMA20 < SMA50) -20')

        # SMA200
        if price and sma200:
            if price > sma200:
                score += 15
                factors.append('Nad SMA200 +15')
            else:
                score -= 15
                factors.append('Pod SMA200 -15')

        # MACD
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                score += 10
                factors.append('MACD pozitivní +10')
            else:
                score -= 10
                factors.append('MACD negativní -10')

        # Weekly momentum
        weekly = price_data.get('weekly_change', 0)
        if weekly > 5:
            score += 10
            factors.append(f'Týdenní +{weekly}% +10')
        elif weekly < -5:
            score -= 10
            factors.append(f'Týdenní {weekly}% -10')

        return {'score': score, 'factors': factors}


# ============================================================================
# MAIN - Run analysis
# ============================================================================

def run_full_analysis(symbol: str) -> Dict:
    """Run complete analysis for a symbol"""

    calculator = SmartScoreCalculator()

    # Get data from Supabase
    # Prices
    prices = supabase_get('finance_prices', {
        'select': 'date,close,volume',
        'symbol': f'eq.{symbol}',
        'order': 'date.desc',
        'limit': '10'
    })

    # Indicators
    indicators = supabase_get('finance_indicators', {
        'select': '*',
        'symbol': f'eq.{symbol}',
        'order': 'date.desc',
        'limit': '1'
    })

    # Stock info
    stocks = supabase_get('finance_stocks', {
        'select': '*',
        'symbol': f'eq.{symbol}'
    })

    if not prices or not indicators:
        return {'error': f'No data for {symbol}'}

    price_data = {
        'price': prices[0]['close'] if prices else 0,
        'weekly_change': ((prices[0]['close'] - prices[-1]['close']) / prices[-1]['close'] * 100) if len(prices) > 1 else 0
    }

    indicator_data = indicators[0] if indicators else {}
    stock_info = stocks[0] if stocks else {}

    # For now, fundamentals from stock_info (would be separate table)
    fundamental_data = {
        'pe_ratio': None,  # Would come from Yahoo Finance
        'profit_margin': None,
        'revenue_growth': None,
        'return_on_equity': None,
        'debt_to_equity': None,
    }

    result = calculator.calculate_smart_score(
        symbol, price_data, indicator_data, fundamental_data, stock_info
    )

    return result


if __name__ == '__main__':
    # Test
    print("Testing Smart Analysis System...")

    # Test backtest
    engine = BacktestEngine()
    result = engine.backtest_symbol('AAPL', 'combined')
    print(f"\nBacktest AAPL: {json.dumps(result, indent=2, default=str)}")

    # Test full analysis
    analysis = run_full_analysis('AAPL')
    print(f"\nFull Analysis AAPL: {json.dumps(analysis, indent=2, default=str)}")
