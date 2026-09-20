import numpy as np
import pandas as pd

def run_monte_carlo():
    np.random.seed(42)
    n_simulations = 10000
    n_trades = 300
    initial_capital = 10000.0
    stake = 25.0  # 0.25% fixed
    payout = 0.85 # 85% typical payout

    win_rates = [0.473, 0.500, 0.530, 0.550, 0.580, 0.600]

    results = []

    print("================================================================================")
    print("MONTE CARLO SIMULATION: 10,000 SIMULATIONS OF 300 TRADES (FLAT STAKE $25 / 0.25%)")
    print(f"Initial Capital: ${initial_capital:,.2f} | Stake: ${stake:.2f} | Payout: {payout*100:.0f}%")
    print("Break-even Win Rate required: 54.05%")
    print("================================================================================\n")

    for wr in win_rates:
        # Generate random outcomes: shape (n_simulations, n_trades)
        outcomes = np.random.binomial(1, wr, size=(n_simulations, n_trades))
        
        # Calculate PnL per trade: win -> +stake * payout, loss -> -stake
        pnl_matrix = np.where(outcomes == 1, stake * payout, -stake)
        
        # Cumulative equity curves: shape (n_simulations, n_trades)
        equity_curves = initial_capital + np.cumsum(pnl_matrix, axis=1)
        # Prepend initial capital
        equity_curves = np.hstack([np.full((n_simulations, 1), initial_capital), equity_curves])

        # Final equities
        final_equities = equity_curves[:, -1]
        net_profits = final_equities - initial_capital

        # Calculate Max Drawdown for each simulation
        peak = np.maximum.accumulate(equity_curves, axis=1)
        drawdowns = peak - equity_curves
        drawdown_pcts = drawdowns / peak * 100.0
        max_drawdowns_usd = np.max(drawdowns, axis=1)
        max_drawdowns_pct = np.max(drawdown_pcts, axis=1)

        # Consecutive losing streaks
        def max_consecutive_zeros(row):
            max_streak = 0
            cur = 0
            for x in row:
                if x == 0:
                    cur += 1
                    if cur > max_streak:
                        max_streak = cur
                else:
                    cur = 0
            return max_streak

        losing_streaks = np.apply_along_axis(max_consecutive_zeros, 1, outcomes)

        # Probability of profit
        prob_profit = np.mean(net_profits > 0) * 100.0
        prob_ruin = np.mean(final_equities <= 0) * 100.0

        ev_per_trade = (wr * (stake * payout)) - ((1 - wr) * stake)

        results.append({
            "Win Rate": f"{wr*100:.1f}%",
            "EV/Trade": f"${ev_per_trade:+.2f}",
            "Expected 300T PnL": f"${np.mean(net_profits):+,.2f}",
            "Median Final Equity": f"${np.median(final_equities):,.2f}",
            "Prob Profit": f"{prob_profit:.1f}%",
            "Max DD (Avg)": f"${np.mean(max_drawdowns_usd):,.2f} ({np.mean(max_drawdowns_pct):.2f}%)",
            "Max DD (95% Worst)": f"${np.percentile(max_drawdowns_usd, 95):,.2f} ({np.percentile(max_drawdowns_pct, 95):.2f}%)",
            "Max DD (99% Worst)": f"${np.percentile(max_drawdowns_usd, 99):,.2f} ({np.percentile(max_drawdowns_pct, 99):.2f}%)",
            "Avg Max Loss Streak": f"{np.mean(losing_streaks):.1f} trades",
            "Worst Loss Streak (99%)": f"{np.percentile(losing_streaks, 99):.0f} trades",
        })

    df_res = pd.DataFrame(results)
    print(df_res.to_string(index=False))

    # Also simulate what happens with Martingale ($25 -> $55) at 47.3% and 52%
    print("\n\n================================================================================")
    print("COMPARISON: 2-STEP MARTINGALE ($25 -> $55) vs FLAT STAKE ($25) at 47.3% WIN RATE")
    print("================================================================================")
    # Martingale simulation
    mart_outcomes = np.random.binomial(1, 0.473, size=(n_simulations, n_trades))
    mart_finals = []
    mart_max_dds = []
    for sim in range(n_simulations):
        eq = initial_capital
        peak_eq = eq
        max_dd = 0
        step = 1
        for res in mart_outcomes[sim]:
            curr_stake = 25.0 if step == 1 else 55.0
            if res == 1:
                eq += curr_stake * payout
                step = 1
            else:
                eq -= curr_stake
                step = 2 if step == 1 else 1 # reset to step 1 after 2 steps
            if eq > peak_eq:
                peak_eq = eq
            dd = peak_eq - eq
            if dd > max_dd:
                max_dd = dd
        mart_finals.append(eq)
        mart_max_dds.append(max_dd)

    print(f"2-Step Martingale at 47.3% WR:")
    print(f"  Average Final Balance: ${np.mean(mart_finals):,.2f} (Loss: ${initial_capital - np.mean(mart_finals):,.2f})")
    print(f"  Max Drawdown 95th percentile: ${np.percentile(mart_max_dds, 95):,.2f} ({np.percentile(mart_max_dds, 95)/initial_capital*100:.1f}%)")
    print(f"  Probability of being in profit after 300 trades: {np.mean(np.array(mart_finals) > initial_capital)*100:.1f}%")

if __name__ == "__main__":
    run_monte_carlo()
