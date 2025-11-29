# Probabilistic Trading System - Requirements & Implementation Plan

## 📋 Requirements Summary

**Goal:** Calculate per-bar (1-minute) probability of achieving profit target before hitting stop-loss for both buy and sell trades.

### Key Parameters
- **`profit_target_pct`** (formerly X%) - Target profit percentage to achieve (e.g., 1.0%)
- **`stop_loss_pct`** (formerly Y%) - Maximum loss before exiting (e.g., 0.5%)
- **`risk_limit_pct`** (formerly Z%) - Force exit if stop-loss probability exceeds this (e.g., 70%)

**Example Configuration:**
```python
profit_target_pct = 1.0   # Exit at 1% profit
stop_loss_pct = 0.5       # Exit at 0.5% loss
risk_limit_pct = 70.0     # Force exit if 70%+ chance of hitting stop-loss
```

### Input
- Historical OHLCV data (1-minute bars)
- CSV files per equity
- Configurable parameters: `profit_target_pct`, `stop_loss_pct`, `risk_limit_pct`

### Output
- Buy probability per bar
- Sell probability per bar
- Optimized weight matrix
- Trade signals (buy/sell/exit)

---

## 🤖 Claude Opus 4.1 vs Traditional Implementation

### Option 1: **Claude Opus 4.1 Approach** (RECOMMENDED)

#### ✅ **Advantages:**

1. **Pattern Recognition Excellence**
   - Claude can analyze complex price patterns (head & shoulders, flags, etc.)
   - Natural language understanding of market context
   - Can synthesize multiple indicators into coherent analysis

2. **Adaptive Learning**
   - Can adjust analysis based on recent market behavior
   - Understands market regime changes
   - Can explain reasoning (interpretability)

3. **Rapid Prototyping**
   - Start analyzing immediately without building ML models
   - Iterate on strategy quickly with prompt engineering
   - No training data preparation needed initially

4. **Multi-Modal Analysis**
   - Can combine technical indicators, price action, volume, AND market news
   - Contextual understanding (e.g., "This pattern typically fails in low volatility")
   - Can provide confidence levels naturally

#### ❌ **Disadvantages:**

1. **Cost**
   - ~$0.10-0.30 per 1-minute bar analysis (expensive for backtesting)
   - 1000 bars = ~$100-300
   - Need cost optimization strategies

2. **Latency**
   - 1-3 second response time per request
   - Not suitable for real-+time sub-second trading
   - Better for minute-bar or higher timeframes

3. **Consistency**
   - Outputs may vary slightly between runs
   - Need structured output formatting
   - Requires careful prompt engineering

4. **No Native Probability Calibration**
   - Claude provides confidence, not calibrated probabilities
   - Need to validate/calibrate outputs against historical data

---

### Option 2: **Traditional ML/Statistical Approach**

#### ✅ **Advantages:**

1. **Speed & Cost**
   - Microsecond inference once trained
   - No per-prediction API costs
   - Scalable to millions of bars

2. **Deterministic**
   - Same input = same output
   - Easier to test and validate
   - Reproducible results

3. **Calibrated Probabilities**
   - Proper probability outputs (0-1)
   - Can use techniques like Platt scaling
   - Backtesting is straightforward

4. **Optimized for Time Series**
   - LSTM, GRU, Transformers designed for sequences
   - Can learn temporal dependencies
   - Feature engineering well-established

#### ❌ **Disadvantages:**

1. **Development Time**
   - Months to build, train, validate
   - Requires ML expertise
   - Complex pipeline (feature engineering, training, deployment)

2. **Data Requirements**
   - Need large labeled datasets
   - Historical data quality critical
   - Retraining needed as markets change

3. **Limited Interpretability**
   - Black box predictions
   - Hard to understand why a prediction was made
   - Difficult to debug

4. **Rigid**
   - Can't easily adapt to new patterns
   - Retraining is expensive
   - Doesn't understand context like news events

---

## 🎯 **HYBRID APPROACH (BEST SOLUTION)**

### Architecture

```
┌─────────────────────────────────────────────────────┐
│         1-Minute Bar Data (OHLCV)                   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  Feature Engineering Layer (Traditional)             │
│  - Calculate all technical indicators                │
│  - Price patterns, volume, volatility                │
│  - Support/resistance, trends                        │
│  - FAST: <1ms per bar                                │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌──────────────┐    ┌────────────────────┐
│ Quick Filter │    │   Claude Analysis  │
│ (Traditional)│    │   (Deep Insight)   │
│              │    │                    │
│ - Fast rules │    │ - Pattern recog.   │
│ - Thresholds │    │ - Context          │
│ - Eliminate  │    │ - Confidence       │
│   obvious    │    │ - Reasoning        │
│   cases      │    │                    │
│              │    │ Only for:          │
│ Cost: $0     │    │ - Uncertain cases  │
│ Time: <1ms   │    │ - High stakes      │
│              │    │ - Review           │
│              │    │                    │
│              │    │ Cost: ~$0.10/call  │
│              │    │ Time: 1-2s         │
└──────┬───────┘    └────────┬───────────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │  Decision Aggregation  │
      │  - Combine signals     │
      │  - Weight by accuracy  │
      │  - Output probability  │
      └───────────┬───────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │  Trade Signal          │
      │  - Buy probability     │
      │  - Sell probability    │
      │  - Confidence score    │
      │  - Exit trigger        │
      └───────────────────────┘
```

### Implementation Strategy

#### **Phase 1: Traditional Foundation (Week 1-2)**
✅ Fast, cheap, handles 95% of cases
```python
# Quick probability estimation
if RSI > 70 and volume_spike:
    sell_probability = 0.75  # High confidence
    skip_claude = True
elif clear_downtrend and RSI < 30:
    buy_probability = 0.70
    skip_claude = True
```

#### **Phase 2: Claude Enhancement (Week 3-4)**
🤖 Deep analysis for edge cases
```python
# Use Claude for:
# 1. Ambiguous patterns
# 2. Conflicting signals
# 3. Novel market conditions
# 4. High-value trades (>$10k)

if signals_conflicting() or high_uncertainty():
    claude_analysis = ask_claude_probability(
        bar_data=current_bar,
        indicators=calculated_indicators,
        context=recent_market_behavior
    )
```

#### **Phase 3: Optimization (Week 5-6)**
📊 Backtest and optimize weights
```python
# Optimize weights using historical data
weights = optimize_weights(
    historical_data=last_6_months,
    traditional_signals=traditional_probs,
    claude_signals=claude_probs,
    actual_outcomes=labeled_data
)
```

---

## 📐 Detailed Implementation Plan

### 1. **Data Pipeline**

#### 1.1 CSV Ingestion
```python
# app/services/data_ingestion.py
class OHLCVDataLoader:
    def load_csv(self, filepath: str) -> pd.DataFrame
    def validate_data(self, df: pd.DataFrame) -> bool
    def resample_to_1min(self, df: pd.DataFrame) -> pd.DataFrame
```

#### 1.2 Feature Engineering
```python
# app/services/technical_indicators.py
class IndicatorCalculator:
    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        # VWAP, SMA, EMA, RSI, MACD, Bollinger Bands
        # ATR, ADX, Volume metrics
        # Support/Resistance levels
        # Pattern detection
```

### 2. **Probability Engine**

#### 2.1 Traditional Probability Model
```python
# app/services/probability_engine.py
class TraditionalProbabilityModel:
    def calculate_buy_probability(
        self,
        bar: Dict,
        indicators: Dict,
        params: ProbabilityParams
    ) -> float:
        """
        Fast rule-based probability calculation
        Returns: 0.0 to 1.0
        """
        
    def calculate_sell_probability(...) -> float
    
    def should_force_exit(
        self,
        stop_loss_prob: float,
        threshold_z: float
    ) -> bool
```

#### 2.2 Claude-Enhanced Model
```python
# app/services/claude_probability.py
class ClaudeProbabilityAnalyzer:
    async def analyze_probability(
        self,
        bar_data: Dict,
        indicators: Dict,
        context: Dict
    ) -> ProbabilityAnalysis:
        """
        Use Claude for deep pattern analysis
        
        Returns:
            buy_prob: float
            sell_prob: float
            confidence: float
            reasoning: str
            stop_loss_risk: float
        """
        
        prompt = self._build_probability_prompt(
            bar_data, indicators, context
        )
        
        response = claude_client.ask(prompt)
        
        return self._parse_probability_response(response)
```

### 3. **Optimization System**

#### 3.1 Weight Optimization
```python
# app/services/weight_optimizer.py
class WeightOptimizer:
    def optimize_weights(
        self,
        historical_data: pd.DataFrame,
        profit_target_x: float,
        stop_loss_y: float
    ) -> Dict[str, float]:
        """
        Optimize indicator weights to maximize success rate
        
        Uses:
        - Grid search
        - Genetic algorithms
        - Or Bayesian optimization
        """
```

#### 3.2 Backtesting Engine
```python
# app/services/backtester.py
class Backtester:
    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy: ProbabilityStrategy,
        params: BacktestParams
    ) -> BacktestResults:
        """
        Simulate trades on historical data
        Calculate win rate, profit factor, etc.
        """
```

### 4. **Real-Time Trading Engine**

```python
# app/services/trading_engine.py
class ProbabilityTradingEngine:
    async def process_bar(
        self,
        bar: BarData,
        use_claude: bool = False
    ) -> TradeSignal:
        """
        1. Calculate indicators
        2. Get traditional probability
        3. Optionally enhance with Claude
        4. Check exit conditions
        5. Return trade signal
        """
```

---

## 💰 Cost Analysis

### Traditional Only
- **Cost:** $0 per bar
- **Speed:** <1ms per bar
- **Accuracy:** 60-70% (typical)

### Claude Only
- **Cost:** ~$0.15 per bar (1500 tokens avg)
- **Speed:** 1-2 seconds per bar
- **Accuracy:** 70-80% (estimated)
- **1000 bars:** $150

### Hybrid (Recommended)
- **Cost:** ~$0.015 per bar (10% use Claude)
- **Speed:** Average 100ms per bar
- **Accuracy:** 75-85% (best of both)
- **1000 bars:** $15

**Cost Breakdown Explained:**
- 1000 bars = ~2.5 trading days (1 day = 390 1-minute bars)
- Hybrid uses Claude for 10% of bars = 100 Claude API calls
- Each call: ~1500 tokens @ $15/M input + $75/M output
- Average: ~$0.15 per call × 100 calls = **$15 total**

**Real-World Scenarios:**
- **1 week backtest** (5 days) = 1,950 bars = ~$29
- **1 month backtest** (21 days) = 8,190 bars = ~$123
- **6 months backtest** (126 days) = 49,140 bars = ~$737
- **Live trading (1 day)** = 390 bars = ~$6
- **Live trading (1 month)** = ~8,190 bars = ~$123

---

## 🚀 Implementation Timeline

### **Week 1-2: Foundation**
- [ ] Data ingestion pipeline
- [ ] Technical indicator calculation
- [ ] Traditional probability model
- [ ] Backtesting framework

### **Week 3-4: Claude Integration**
- [ ] Claude probability prompts
- [ ] Response parsing
- [ ] Hybrid decision logic
- [ ] Cost optimization

### **Week 5-6: Optimization**
- [ ] Weight optimization system
- [ ] Backtest with historical data
- [ ] A/B test traditional vs hybrid
- [ ] Fine-tune thresholds

### **Week 7-8: Production**
- [ ] Real-time data integration
- [ ] Live trading (paper first)
- [ ] Monitoring & alerting
- [ ] Performance tracking

---

## 🎓 Recommendation

### **Start with Hybrid Approach**

**Phase 1 (Now):**
1. Build traditional probability model first
2. Get baseline performance
3. Identify where it struggles

**Phase 2 (After baseline):**
1. Add Claude for uncertain cases
2. Compare performance
3. Optimize when to use Claude

**Phase 3 (Optimization):**
1. Backtest extensively
2. Optimize weights & thresholds
3. Minimize Claude usage while maximizing accuracy

### **Why Hybrid Wins:**

1. **Best accuracy** (combine both strengths)
2. **Manageable cost** (selective Claude usage)
3. **Fast enough** for 1-min bars
4. **Interpretable** (Claude explains reasoning)
5. **Adaptable** (can tune Claude usage based on market conditions)

---

## 📊 Example Workflow

```python
# Real-time trading
async def process_1min_bar(bar: BarData):
    # Calculate indicators (fast)
    indicators = calculate_indicators(bar)
    
    # Quick traditional probability
    trad_buy_prob = traditional_model.buy_probability(bar, indicators)
    trad_sell_prob = traditional_model.sell_probability(bar, indicators)
    
    # Check if we need Claude
    uncertainty = abs(trad_buy_prob - trad_sell_prob)
    use_claude = (
        uncertainty < 0.2 or  # Too close to call
        max(trad_buy_prob, trad_sell_prob) > 0.85 or  # High stakes
        is_pattern_complex(indicators)  # Complex pattern
    )
    
    if use_claude:
        # Deep analysis
        claude_analysis = claude_analyzer.analyze(
            bar, indicators, recent_context
        )
        
        # Combine probabilities
        final_buy_prob = (
            0.3 * trad_buy_prob + 
            0.7 * claude_analysis.buy_prob
        )
        final_sell_prob = (
            0.3 * trad_sell_prob + 
            0.7 * claude_analysis.sell_prob
        )
    else:
        final_buy_prob = trad_buy_prob
        final_sell_prob = trad_sell_prob
    
    # Check exit condition
    if claude_analysis.stop_loss_risk > Z_THRESHOLD:
        return TradeSignal.EXIT
    
    # Return signal
    if final_buy_prob > 0.75:
        return TradeSignal.BUY
    elif final_sell_prob > 0.75:
        return TradeSignal.SELL
    else:
        return TradeSignal.HOLD
```

---

## 🔧 Technical Stack

**Backend:**
- Python 3.11 (your embedded environment ✓)
- Pandas + NumPy (data processing)
- TA-Lib or pandas-ta (technical indicators)
- FastAPI (API endpoints) ✓
- SQLite (historical data storage) ✓
- Claude Opus 4.1 (AI analysis) ✓

**Libraries Needed:**
```txt
pandas==2.2.0  # Already have ✓
numpy==1.26.3  # Already have ✓
pandas-ta==0.3.14b  # For technical indicators
scipy==1.12.0  # For optimization
scikit-learn==1.4.0  # For ML utilities
```

---

## 📈 Success Metrics

1. **Win Rate:** % of trades hitting profit before stop-loss
2. **Profit Factor:** Gross profit / gross loss
3. **Sharpe Ratio:** Risk-adjusted returns
4. **Max Drawdown:** Largest peak-to-trough decline
5. **Claude ROI:** Additional profit from Claude / Claude costs

**Target:** 65%+ win rate with X=1%, Y=0.5%

---

**Next Step:** Should I start implementing Phase 1 (Traditional Foundation) or would you like to explore the Claude probability prompting strategy first?
