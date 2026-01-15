import pandas as pd
import numpy as np

# Balancer LBP Swap Fee (0.15% - standard from the original spreadsheet)
SWAP_FEE = 0.0015

# Note: This simulator implements a mathematical model of Balancer LBP mechanics.
# Real-world LPBs may have additional factors like gas costs, MEV, and liquidity provider behavior. 

def get_spot_price(token_a_balance: float, token_b_balance: float, token_a_weight: float, token_b_weight: float) -> float:
    """
    Calculates the pool's market price (Spot Price): Price (Token B / Token A).
    Formula: (Balance_B / Weight_B) / (Balance_A / Weight_A)
    """
    if token_a_balance <= 0 or token_b_balance <= 0 or token_a_weight <= 0 or token_b_weight <= 0:
        return 0
    
    return (token_b_balance / token_b_weight) / (token_a_balance / token_a_weight)

def derive_weight_from_price(token_a_balance: float, token_b_balance: float, desired_price: float) -> float:
    """
    Derives the required Token A weight (W_A) to achieve a Desired Price (P).
    W_A = 1 / (1 + (B_B / (B_A * P)))
    """
    if token_a_balance == 0 or desired_price <= 0:
        return 0.9

    # R = (B_B / (B_A * P_desired))
    ratio = token_b_balance / (token_a_balance * desired_price)
    
    # W_A = 1 / (1 + R)
    weight_a = 1.0 / (1.0 + ratio)
    
    # Ensure weight is within a valid range
    return np.clip(weight_a, 0.01, 0.99)

def calculate_token_a_sold(token_b_bought: float, token_a_balance: float, token_b_balance: float, token_a_weight: float, token_b_weight: float) -> float:
    """
    Calculates the amount of Token A (TKN, output) sold for a fixed amount of
    Token B (USDC, input), using the Balancer V2 LBP formula (Fixed Input with Fee on Input).

    Token B is Input, Token A is Output.

    This preserves the Balancer invariant: ∏(B_i^W_i) = constant
    Formula: O_A = B_A * (1 - R^(-W_B/W_A)) where R = (B_B + I_B_net) / B_B
    """
    if token_b_bought <= 0:
        return 0

    # Net Token B input after fee
    token_b_bought_net = token_b_bought * (1.0 - SWAP_FEE)
    
    # Ratio of new Token B balance to old balance
    # R_B = (B_B_old + I_B_Net) / B_B_old
    ratio_b = (token_b_balance + token_b_bought_net) / token_b_balance
    
    if ratio_b <= 0:
        return token_a_balance

    # Invariant formula for Token A output: O_A = B_A_old * ( 1 - (R_B)**(-W_B/W_A) )
    exponent = -token_b_weight / token_a_weight
    
    try:
        # Calculate Token A sold (output)
        token_a_sold = token_a_balance * (1.0 - ratio_b**exponent)
    except Exception:
        return 0
    
    # Clamp to prevent selling more TKN than available
    # This handles edge cases where extreme parameters might cause overselling
    return np.clip(token_a_sold, 0, token_a_balance)

def calculate_slippage(
    price_before: float, 
    price_after: float
) -> float:
    """
    Calculate slippage as price impact percentage.
    Slippage = (price_after - price_before) / price_before * 100
    
    Returns slippage as a percentage (e.g., 2.5 for 2.5%).
    Positive values indicate price increase (buying pressure).
    """
    if price_before <= 0:
        return 0.0
    
    slippage_pct = ((price_after - price_before) / price_before) * 100.0
    return slippage_pct

def generate_gaussian_demand_curve(
    total_demand: float,
    duration_hours: int,
    peak_position: float = 0.5,
    curve_width: float = 0.2
) -> np.ndarray:
    """
    Generate a Gaussian (bell curve) demand distribution over time.
    
    Parameters:
        total_demand: Total demand over the entire duration
        duration_hours: Number of hours in the simulation
        peak_position: Position of the peak as fraction of duration (0.0 to 1.0, default 0.5 = middle)
        curve_width: Standard deviation as fraction of duration (smaller = narrower peak, default 0.2)
    
    Returns:
        Array of hourly demand values following a Gaussian distribution
    """
    # Create time points (0 to duration_hours)
    hours = np.arange(duration_hours + 1)
    
    # Normalize to 0-1 range
    normalized_hours = hours / duration_hours if duration_hours > 0 else hours
    
    # Calculate mean (peak position) and std (curve width) in normalized space
    mean = peak_position
    std = curve_width
    
    # Generate Gaussian distribution
    gaussian = np.exp(-0.5 * ((normalized_hours - mean) / std) ** 2)
    
    # Normalize so the sum equals total_demand
    # We exclude hour 0 (no swaps) from the total
    gaussian_sum = gaussian[1:].sum() if len(gaussian) > 1 else 1.0
    if gaussian_sum > 0:
        normalized_gaussian = gaussian / gaussian_sum * total_demand
    else:
        normalized_gaussian = gaussian * total_demand
    
    # Set hour 0 to 0 (no demand at start)
    normalized_gaussian[0] = 0.0
    
    return normalized_gaussian

def run_simulation(params: dict) -> pd.DataFrame:
    """
    Runs the LBP simulation hour by hour based on constant Token B demand 
    and price-derived weights.
    
    Parameters:
        params: Dictionary containing:
            - duration_hours: Total hours for simulation
            - initial_token_a: Initial Token A balance
            - initial_token_b: Initial Token B balance
            - start_price: Starting price
            - end_price: Ending price
            - demand_per_hour_token_b: Default hourly demand
            - demand_overrides: Optional list of dicts with 'target_price' and 'demand'
    """
    
    hours = params['duration_hours']
    token_a_balance = params['initial_token_a']
    token_b_balance = params['initial_token_b']
    
    # Get demand overrides (list of {target_price, demand})
    demand_overrides = params.get('demand_overrides', [])
    
    # Track which overrides have been triggered (to avoid multiple triggers)
    triggered_overrides = set()
    
    # 1. Weight Derivation - Calculate weights needed to achieve start and end prices
    # Weights are calculated from initial balances and target prices
    start_price = params['start_price']
    end_price = params['end_price']
    
    # Calculate start and end weights from initial balances
    start_weight = derive_weight_from_price(
        token_a_balance, token_b_balance, start_price
    )
    end_weight = derive_weight_from_price(
        token_a_balance, token_b_balance, end_price
    )
    
    # Generate linear weight progression (this creates the natural downward price trend)
    weights = np.linspace(start_weight, end_weight, hours + 1)
    
    # Calculate baseline prices (price without any buy pressure, just weight shifts)
    # This shows the natural downward price trend in LBP as weights shift from high Token A weight to low
    # Uses initial balances throughout - trading activity doesn't affect the predetermined weight schedule
    baseline_prices = []
    baseline_token_a_balance = token_a_balance
    baseline_token_b_balance = token_b_balance
    for i in range(hours + 1):
        # Use the predetermined weight progression
        baseline_weight = weights[i]
        baseline_token_b_weight = 1.0 - baseline_weight
        baseline_price = get_spot_price(
            baseline_token_a_balance,
            baseline_token_b_balance,
            baseline_weight,
            baseline_token_b_weight
        )
        baseline_prices.append(baseline_price)
    
    # 2. Simulation Logic - Generate demand curve
    # Check if demand_curve is provided, otherwise use constant demand
    if 'demand_curve' in params and params['demand_curve'] is not None:
        hourly_demand_curve = params['demand_curve']
    else:
        # Fallback to constant demand
        default_demand_per_hour = params.get('demand_per_hour_token_b', 0.0)
        hourly_demand_curve = np.full(hours + 1, default_demand_per_hour)
        hourly_demand_curve[0] = 0.0  # No demand at hour 0
    
    data = [] 
    cumulative_proceeds_token_b = 0.0
    previous_price = None  # Track previous hour's price to detect threshold crossing

    for i in range(hours + 1): 
        
        # Use predetermined weight progression (weights shift independently of balances)
        # This creates the natural downward price trend in LBP - core mechanism of price discovery
        # Unlike regular AMMs, LBP weights follow a fixed schedule regardless of trading volume
        token_a_weight = weights[i]
        token_b_weight = 1.0 - token_a_weight
        
        # Price calculated BEFORE the swap for the current hour
        price_before_swap = get_spot_price(token_a_balance, token_b_balance, token_a_weight, token_b_weight)
        
        # Initialize price_after_swap (will be calculated if swap happens)
        price_after_swap = price_before_swap
        
        token_a_sold_this_hour = 0.0
        token_b_gained_this_hour = 0.0
        slippage_pct = 0.0
        override_applied = False
        override_price = None

        if i > 0:
            
            # --- Demand Logic with Price-Based Overrides ---
            # Start with base demand from curve for this hour
            token_b_demand_this_hour = hourly_demand_curve[i]
            
            for override_idx, override in enumerate(demand_overrides):
                target_price = override['target_price']
                override_id = override_idx  # Use index as unique identifier
                
                # Check if we're crossing the threshold from above (previous > target, current <= target)
                # and this override hasn't been triggered yet
                # This simulates a bot that triggers exactly when price reaches the target
                if (previous_price is not None and 
                    previous_price > target_price and 
                    price_before_swap <= target_price and 
                    override_id not in triggered_overrides):
                    token_b_demand_this_hour = override['demand']
                    triggered_overrides.add(override_id)
                    override_applied = True
                    override_price = target_price
                    break  # Only apply first matching override
            
            # 1. Token B bought (Input, demand may be overridden)
            token_b_gained_this_hour = token_b_demand_this_hour
            
            # 2. Token A sold (Output, calculated via Balancer formula)
            token_a_sold_this_hour = calculate_token_a_sold(
                token_b_gained_this_hour, 
                token_a_balance, 
                token_b_balance, 
                token_a_weight, 
                token_b_weight
            )
            
            # Check if pool is drained
            if token_a_sold_this_hour == 0 or token_a_balance - token_a_sold_this_hour < 1e-9:
                token_a_sold_this_hour = 0
                token_b_gained_this_hour = 0
                price_after_swap = price_before_swap  # No change if pool is drained
            else:
                # Calculate price after swap to determine slippage
                token_a_balance_after = token_a_balance - token_a_sold_this_hour
                token_b_balance_after = token_b_balance + token_b_gained_this_hour
                price_after_swap = get_spot_price(
                    token_a_balance_after, 
                    token_b_balance_after, 
                    token_a_weight, 
                    token_b_weight
                )
                
                # Calculate slippage (price impact)
                slippage_pct = calculate_slippage(price_before_swap, price_after_swap)
        
        data.append({
            'hour': i,
            'price': price_before_swap,
            'baseline_price': baseline_prices[i],
            'token_a_balance': token_a_balance,
            'token_b_balance': token_b_balance,
            'token_a_weight': token_a_weight,
            'token_b_weight': token_b_weight,
            'token_a_sold': token_a_sold_this_hour,
            'token_b_gained': token_b_gained_this_hour,
            'slippage_pct': slippage_pct,
            'override_applied': override_applied,
            'override_price': override_price if override_applied else None,
            'cumulative_proceeds_token_b': cumulative_proceeds_token_b,
            'start_weight': start_weight,
            'end_weight': end_weight
        })
        
        # Update balances and track price for threshold detection
        if i < hours:
            token_a_balance -= token_a_sold_this_hour
            token_b_balance += token_b_gained_this_hour
            cumulative_proceeds_token_b += token_b_gained_this_hour
            
            # Update previous_price for threshold crossing detection in next iteration
            # This is the price after the swap (or before if no swap), which will be compared
            # to the next hour's price_before_swap to detect threshold crossing
            previous_price = price_after_swap

    return pd.DataFrame(data)