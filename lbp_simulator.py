import pandas as pd
import numpy as np

# Balancer LBP Swap Fee (0.15% - standard from the original spreadsheet)
SWAP_FEE = 0.0015 

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
            - demand_overrides: Optional dict mapping hour -> demand override value
    """
    
    hours = params['duration_hours']
    token_a_balance = params['initial_token_a']
    token_b_balance = params['initial_token_b']
    
    # Get demand overrides (default to empty dict)
    demand_overrides = params.get('demand_overrides', {})
    
    # 1. Weight Derivation
    start_weight = derive_weight_from_price(
        token_a_balance, token_b_balance, params['start_price']
    )
    end_weight = derive_weight_from_price(
        token_a_balance, token_b_balance, params['end_price']
    )
    
    # Generate linear weight progression
    weights = np.linspace(start_weight, end_weight, hours + 1)
    
    # 2. Simulation Logic
    default_demand_per_hour = params['demand_per_hour_token_b']
    
    data = [] 
    cumulative_proceeds_token_b = 0.0

    for i in range(hours + 1): 
        
        token_a_weight = weights[i]
        token_b_weight = 1.0 - token_a_weight
        
        # Price calculated BEFORE the swap for the current hour
        price_before_swap = get_spot_price(token_a_balance, token_b_balance, token_a_weight, token_b_weight)
        
        token_a_sold_this_hour = 0.0
        token_b_gained_this_hour = 0.0
        slippage_pct = 0.0

        if i > 0:
            
            # --- Demand Logic with Overrides ---
            # Check if there's an override for this hour, otherwise use default
            token_b_demand_this_hour = demand_overrides.get(i, default_demand_per_hour)
            
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
            'token_a_balance': token_a_balance,
            'token_b_balance': token_b_balance,
            'token_a_weight': token_a_weight,
            'token_b_weight': token_b_weight,
            'token_a_sold': token_a_sold_this_hour,
            'token_b_gained': token_b_gained_this_hour,
            'slippage_pct': slippage_pct,
            'cumulative_proceeds_token_b': cumulative_proceeds_token_b,
            'start_weight': start_weight, 
            'end_weight': end_weight      
        })
        
        # Update balances for the next iteration
        if i < hours:
            token_a_balance -= token_a_sold_this_hour
            token_b_balance += token_b_gained_this_hour
            cumulative_proceeds_token_b += token_b_gained_this_hour

    return pd.DataFrame(data)