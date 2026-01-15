import streamlit as st
import pandas as pd
import lbp_simulator 
import numpy as np 

COMMON_TOKENS = ["TKN", "USDC", "DAI", "USDT", "WETH", "WBTC", "Custom..."]

st.set_page_config(
    page_title="LBP Simulator",  
    page_icon="images/balancer.png", 
    layout="wide"
)

st.title("LBP Simulator")
st.sidebar.title("Simulation Setup")
st.sidebar.markdown("---")

# --- 1. Project, Tokens, and Duration ---
with st.sidebar.container(border=True):
    st.subheader("1. Project & Tokens")
    
    token_a_selection = st.selectbox(
        "Sale Token (A)", 
        options=COMMON_TOKENS, 
        index=COMMON_TOKENS.index("TKN")
    )
    # The text input for custom name is placed immediately after the selectbox
    token_a_name = st.text_input("Custom Sale Symbol", "MY_TKN") if token_a_selection == "Custom..." else token_a_selection

    token_b_selection = st.selectbox(
        "Collateral Token (B)", 
        options=COMMON_TOKENS, 
        index=COMMON_TOKENS.index("USDC")
    )
    # The text input for custom name is placed immediately after the selectbox
    token_b_name = st.text_input("Custom Collateral Symbol", "USDC") if token_b_selection == "Custom..." else token_b_selection
    
    duration_hours = st.slider("Sale Duration (Hours)", 1, 168, 72, 1)


# --- 2. FDV / Price Parameters ---
with st.sidebar.container(border=True):
    st.subheader("2. Weight Derivation (FDV/Price)")
    
    total_supply = st.number_input(
        f"{token_a_name} Supply (for FDV)",
        value=100000000.0,
        min_value=1.0
    )
    
    # Inputs are now stacked vertically
    fdv_start = st.number_input(
        f"Initial FDV ({token_b_name})",
        value=50000000.0,
        min_value=1.0,
        help="Fully Diluted Valuation at LBP start."
    )
    
    fdv_end = st.number_input(
        f"Final FDV ({token_b_name})",
        value=15000000.0,
        min_value=1.0,
        help="Fully Diluted Valuation at LBP end."
    )
    
    # Calculate initial/final prices
    start_price = fdv_start / total_supply
    end_price = fdv_end / total_supply
    
    st.caption(f"Derived Start Price: **{start_price:,.4f} {token_b_name}**")
    st.caption(f"Derived End Price: **{end_price:,.4f} {token_b_name}**")
    
    st.caption("----")
    st.caption("Pool Balances:")
    
    # Pool Balances Input are also stacked vertically
    initial_token_a = st.number_input(
        f"Initial {token_a_name} Balance (Pool)", 
        value=7500000.0, 
        min_value=1.0
    )
    initial_token_b = st.number_input(
        f"Initial {token_b_name} Balance (Pool)", 
        value=1333333.0, 
        min_value=1.0
    )
    
    # Display derived weights
    try:
        derived_start_weight = lbp_simulator.derive_weight_from_price(
            initial_token_a, initial_token_b, start_price
        )
        derived_end_weight = lbp_simulator.derive_weight_from_price(
            initial_token_a, initial_token_b, end_price
        )
        st.caption(f"Derived Start Weight ({token_a_name}): **{derived_start_weight*100:,.2f}%**")
        st.caption(f"Derived End Weight ({token_a_name}): **{derived_end_weight*100:,.2f}%**")
    except Exception:
        derived_start_weight = np.nan
        derived_end_weight = np.nan
        st.caption("Cannot derive weights. Check balance/price inputs.")


# --- 3. Simulation Demand Parameters ---
with st.sidebar.container(border=True):
    st.subheader("3. Demand Parameters")
    
    demand_per_day_token_b = st.number_input(
        f"Constant Daily Demand (in {token_b_name})",
        value=1000000.0,
        min_value=0.0,
        help=f"Fixed amount of {token_b_name} (Collateral) bought per day."
    )
    
    demand_per_hour_token_b = demand_per_day_token_b / 24
    st.caption(f"Hourly Demand: **{demand_per_hour_token_b:,.2f} {token_b_name}**")


# --- Run Simulation ---
simulation_params = {
    'duration_hours': duration_hours,
    'initial_token_a': initial_token_a,
    'initial_token_b': initial_token_b,
    'start_price': start_price,
    'end_price': end_price,    
    'demand_per_hour_token_b': demand_per_hour_token_b,
}

if st.button("Run Simulation"):
    try:
        results_df = lbp_simulator.run_simulation(simulation_params)
        st.session_state['results_df'] = results_df
        st.session_state['token_names'] = {'A': token_a_name, 'B': token_b_name}
    except Exception as e:
        st.error(f"Error running simulation: {e}. Check if initial balances/prices are valid.")

# --- Display Results ---
if 'results_df' in st.session_state:
    results_df = st.session_state['results_df']
    token_a_name = st.session_state['token_names']['A']
    token_b_name = st.session_state['token_names']['B']
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Price", "Demand", "Balances", "Slippage", "Raw Data"])

    # Extract derived weights from the results (they are constant)
    w_start = results_df['start_weight'].iloc[0]
    w_end = results_df['end_weight'].iloc[0]

    with tab1:
        st.subheader(f"Spot Price ({token_b_name} per {token_a_name})")
        st.line_chart(results_df.set_index('hour')['price'])

    with tab2:
        st.subheader(f"Hourly Sold ({token_a_name})")

        plot_df_demand = results_df.set_index('hour').rename(
            columns={'token_a_sold': f"Sold {token_a_name}/Hour"}
        )
        st.bar_chart(plot_df_demand[f"Sold {token_a_name}/Hour"])

    with tab3:
        st.subheader("Pool Balances")

        plot_df_balances = results_df.set_index('hour').rename(columns={
            'token_a_balance': token_a_name,
            'token_b_balance': token_b_name
        })
        st.line_chart(plot_df_balances[[token_a_name, token_b_name]])

    with tab4:
        st.subheader("Slippage (Price Impact %)")
        st.caption("Slippage represents the percentage change in price due to each hourly swap.")
        
        if 'slippage_pct' in results_df.columns:
            # Filter out hour 0 (no swap happens at hour 0, so slippage is always 0)
            slippage_df = results_df[results_df['hour'] > 0].copy()
            
            if len(slippage_df) > 0:
                plot_df_slippage = slippage_df.set_index('hour').rename(
                    columns={'slippage_pct': 'Slippage (%)'}
                )
                st.line_chart(plot_df_slippage['Slippage (%)'])
                
                # Display slippage statistics (excluding hour 0)
                avg_slippage = slippage_df['slippage_pct'].mean()
                max_slippage = slippage_df['slippage_pct'].max()
                min_slippage = slippage_df['slippage_pct'].min()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Average Slippage", f"{avg_slippage:.4f}%")
                with col2:
                    st.metric("Max Slippage", f"{max_slippage:.4f}%")
                with col3:
                    st.metric("Min Slippage", f"{min_slippage:.4f}%")
            else:
                st.info("No slippage data available (only hour 0 in results).")
        else:
            st.info("Slippage data not available in results.")

    with tab5:
        st.subheader("Derived Parameters Summary")
        summary_weights = pd.DataFrame([
            {'Parameter': f'{token_a_name} Start Weight', 'Value': f'{w_start*100:,.2f}%'},
            {'Parameter': f'{token_a_name} End Weight', 'Value': f'{w_end*100:,.2f}%'}
        ])
        st.table(summary_weights.set_index('Parameter'))

        st.subheader("Raw Simulation Data")
        
        rename_map = {
            'hour': 'Hour',
            'token_a_balance': f"{token_a_name} Balance",
            'token_b_balance': f"{token_b_name} Balance",
            'price': f"Price ({token_b_name})",
            'token_a_sold': f"Sold {token_a_name} (Hourly)",
            'token_b_gained':f"Gained {token_b_name} (Hourly)",
            'token_a_weight':f"{token_a_name} Weight",
            'token_b_weight':f"{token_b_name} Weight",
            'slippage_pct': 'Slippage (%)',
            'cumulative_proceeds_token_b': f"Cumulative Proceeds ({token_b_name})",
        }
        
        display_df = results_df.rename(columns=rename_map)
        
        # Select and format columns for better display
        column_order = [
            'Hour', f"{token_a_name} Weight", f"{token_a_name} Balance", 
            f"{token_b_name} Balance", f"Price ({token_b_name})", 
            'Slippage (%)',
            f"Gained {token_b_name} (Hourly)", f"Sold {token_a_name} (Hourly)", 
            f"Cumulative Proceeds ({token_b_name})"
        ]

        st.dataframe(display_df[column_order])