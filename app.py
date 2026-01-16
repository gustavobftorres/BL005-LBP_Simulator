import streamlit as st
import pandas as pd
import lbp_simulator 
import numpy as np 
import plotly.graph_objects as go

COMMON_TOKENS = ["TKN", "USDC", "DAI", "USDT", "WETH", "WBTC", "Custom..."]

st.set_page_config(
    page_title="LBP Simulator",  
    page_icon="images/balancer.png", 
    layout="wide"
)

st.title("🔬 LBP Simulator")
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
    
    # Show price trend explanation
    if start_price > end_price:
        price_decrease_pct = ((start_price - end_price) / start_price) * 100
        st.info(f"📉 Price decreases by **{price_decrease_pct:.1f}%** over the sale period. This is the natural LBP trend as weights shift to find fair market price.")
    elif start_price < end_price:
        st.warning("⚠️ Start price is lower than end price. In LBP, prices typically start high and decrease.")
    else:
        st.info("ℹ️ Start and end prices are equal. Consider setting different values to see the LBP price discovery mechanism.")
    
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
    
    demand_mode = st.radio(
        "Demand Mode",
        options=["Constant", "Gaussian Curve"],
        index=1,
        help="Constant: Fixed demand per hour. Gaussian: Realistic buy pressure curve peaking in the middle."
    )
    
    # Initialize variables
    demand_curve = None
    demand_per_hour_token_b = 0.0
    avg_hourly_demand = 0.0  # For comparison in override display
    
    if demand_mode == "Constant":
        demand_per_day_token_b = st.number_input(
            f"Constant Daily Demand (in {token_b_name})",
            value=1000000.0,
            min_value=0.0,
            help=f"Fixed amount of {token_b_name} (Collateral) bought per day."
        )
        demand_per_hour_token_b = demand_per_day_token_b / 24
        avg_hourly_demand = demand_per_hour_token_b
        st.caption(f"Hourly Demand: **{demand_per_hour_token_b:,.2f} {token_b_name}**")
    else:
        # Gaussian Curve Mode
        total_demand = st.number_input(
            f"Total Demand (in {token_b_name})",
            value=3000000.0,
            min_value=0.0,
            help=f"Total amount of {token_b_name} bought over the entire sale duration."
        )
        
        peak_position = st.slider(
            "Peak Position",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help="Position of peak demand as fraction of duration (0.5 = middle, 0.3 = early, 0.7 = late)"
        )
        
        curve_width = st.slider(
            "Curve Width",
            min_value=0.05,
            max_value=0.5,
            value=0.2,
            step=0.05,
            help="Width of the bell curve (smaller = more concentrated, larger = more spread out)"
        )
        
        # Generate the demand curve
        demand_curve = lbp_simulator.generate_gaussian_demand_curve(
            total_demand=total_demand,
            duration_hours=duration_hours,
            peak_position=peak_position,
            curve_width=curve_width
        )
        
        # Display preview
        avg_hourly_demand = total_demand / duration_hours if duration_hours > 0 else 0
        peak_hourly = demand_curve.max()
        st.caption(f"Peak Hourly Demand: **{peak_hourly:,.2f} {token_b_name}**")
        st.caption(f"Average Hourly Demand: **{avg_hourly_demand:,.2f} {token_b_name}**")
        
        # Show preview chart
        if len(demand_curve) > 1:
            preview_df = pd.DataFrame({
                'hour': range(len(demand_curve)),
                'demand': demand_curve
            })
            st.line_chart(preview_df.set_index('hour')['demand'], height=100)

# --- 4. Demand Overrides (Optional) ---
with st.sidebar.container(border=True):
    st.subheader("4. Demand Overrides (Optional)")
    st.caption("Simulate demand spikes when price reaches target (e.g., whale buys at specific price)")
    
    # Initialize session state for overrides
    if 'demand_overrides' not in st.session_state:
        st.session_state['demand_overrides'] = []
    
    # Display existing overrides
    if st.session_state['demand_overrides']:
        st.write("**Current Overrides:**")
        for idx, override in enumerate(st.session_state['demand_overrides']):
            col1, col2, col3 = st.columns([4, 3, 4])
            with col1:
                st.caption(f"Price ≤ {override['target_price']:,.4f} {token_b_name}: {override['demand']:,.0f} {token_b_name}")
            with col2:
                # Calculate multiplier based on average hourly demand (handles both modes)
                if avg_hourly_demand > 0:
                    multiplier = override['demand'] / avg_hourly_demand
                    st.caption(f"({multiplier:.1f}x avg)")
                else:
                    st.caption("(override)")
            with col3:
                if st.button("×", key=f"remove_{idx}", width='stretch', help="Remove override"):
                    st.session_state['demand_overrides'].pop(idx)
                    st.rerun()
    
    # Add new override
    with st.expander("Add Demand Override"):
        override_target_price = st.number_input(
            f"Target Price ({token_b_name})",
            min_value=0.0,
            value=end_price,
            step=0.0001,
            format="%.4f",
            help="Price threshold - override triggers when price reaches or goes below this value"
        )
        override_demand = st.number_input(
            f"Override Demand ({token_b_name})",
            min_value=0.0,
            value=demand_per_hour_token_b * 5.0,
            help=f"Demand when price target is hit (default: {demand_per_hour_token_b:,.2f} {token_b_name}/hour)"
        )
        
        if st.button("Add Override"):
            # Check if price already has an override (with small tolerance for floating point)
            existing_price = any(abs(o['target_price'] - override_target_price) < 0.0001 
                               for o in st.session_state['demand_overrides'])
            if existing_price:
                st.warning(f"Price {override_target_price:,.4f} already has an override. Remove it first or update it.")
            else:
                st.session_state['demand_overrides'].append({
                    'target_price': override_target_price,
                    'demand': override_demand
                })
                st.rerun()
    
    if st.button("Clear All Overrides"):
        st.session_state['demand_overrides'] = []
        st.rerun()

# --- Run Simulation ---
simulation_params = {
    'duration_hours': duration_hours,
    'initial_token_a': initial_token_a,
    'initial_token_b': initial_token_b,
    'start_price': start_price,
    'end_price': end_price,
    'demand_overrides': st.session_state.get('demand_overrides', []),
}

# Add demand parameters based on mode
if demand_mode == "Constant":
    simulation_params['demand_per_hour_token_b'] = demand_per_hour_token_b
    simulation_params['demand_curve'] = None
else:
    simulation_params['demand_curve'] = demand_curve
    simulation_params['demand_per_hour_token_b'] = 0.0  # Not used in curve mode

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
    
    # Get override hours for indicators (now based on where price targets were hit)
    override_hours = []
    override_prices = []
    if 'override_applied' in results_df.columns and 'override_price' in results_df.columns:
        override_rows = results_df[results_df['override_applied'] == True]
        for _, row in override_rows.iterrows():
            if pd.notna(row['override_price']):
                override_hours.append(row['hour'])
                override_prices.append(row['override_price'])
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Price", "Demand", "Balances", "Slippage", "Raw Data"])

    # Extract derived weights from the results (they are constant)
    w_start = results_df['start_weight'].iloc[0]
    w_end = results_df['end_weight'].iloc[0]

    with tab1:
        st.subheader(f"Spot Price ({token_b_name} per {token_a_name})")
        st.caption("LBP prices start high and decrease as weights shift. Buy pressure can create temporary upward movements.")
        
        # Create plotly chart with baseline and actual price
        fig = go.Figure()
        
        # Add baseline price (without buy pressure)
        if 'baseline_price' in results_df.columns:
            fig.add_trace(go.Scatter(
                x=results_df['hour'],
                y=results_df['baseline_price'],
                mode='lines',
                name='Baseline Price (No Buy Pressure)',
                line=dict(color='#888888', width=2, dash='dash'),
                opacity=0.7
            ))
        
        # Add actual price (with buy pressure)
        fig.add_trace(go.Scatter(
            x=results_df['hour'],
            y=results_df['price'],
            mode='lines',
            name='Actual Price (With Buy Pressure)',
            line=dict(color='#1f77b4', width=2)
        ))
        
        # Add vertical lines for override hours
        for hour, price in zip(override_hours, override_prices):
            if hour <= results_df['hour'].max():
                fig.add_vline(
                    x=hour,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Price: {price:.4f}",
                    annotation_position="top",
                    opacity=0.7
                )
        
        fig.update_layout(
            xaxis_title="Hour",
            yaxis_title=f"Price ({token_b_name})",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, width='stretch')

    with tab2:
        st.subheader("Demand & Sales")
        
        # Show demand curve (buy pressure)
        st.write(f"**Buy Pressure ({token_b_name}/Hour)**")
        fig_demand = go.Figure()
        fig_demand.add_trace(go.Scatter(
            x=results_df['hour'],
            y=results_df['token_b_gained'],
            mode='lines+markers',
            name=f'Demand ({token_b_name})',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4)
        ))
        
        # Add vertical lines for override hours
        for hour, price in zip(override_hours, override_prices):
            if hour <= results_df['hour'].max():
                fig_demand.add_vline(
                    x=hour,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Price: {price:.4f}",
                    annotation_position="top",
                    opacity=0.7
                )
        
        fig_demand.update_layout(
            xaxis_title="Hour",
            yaxis_title=f"Demand ({token_b_name})",
            hovermode='x unified',
            height=300
        )
        st.plotly_chart(fig_demand, width='stretch')
        
        # Show tokens sold
        st.write(f"**Tokens Sold ({token_a_name}/Hour)**")
        fig_sold = go.Figure()
        fig_sold.add_trace(go.Bar(
            x=results_df['hour'],
            y=results_df['token_a_sold'],
            name=f"Sold {token_a_name}/Hour",
            marker_color='#2ca02c'
        ))
        
        # Add vertical lines for override hours
        for hour, price in zip(override_hours, override_prices):
            if hour <= results_df['hour'].max():
                fig_sold.add_vline(
                    x=hour,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Price: {price:.4f}",
                    annotation_position="top",
                    opacity=0.7
                )
        
        fig_sold.update_layout(
            xaxis_title="Hour",
            yaxis_title=f"Sold {token_a_name}",
            hovermode='x unified',
            height=300
        )
        st.plotly_chart(fig_sold, width='stretch')

    with tab3:
        st.subheader("Pool Balances")
        
        # Create plotly chart with override indicators
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=results_df['hour'],
            y=results_df['token_a_weight'],
            mode='lines',
            name=token_a_name,
            line=dict(color='#1f77b4', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=results_df['hour'],
            y=results_df['token_b_weight'],
            mode='lines',
            name=token_b_name,
            line=dict(color='#ff7f0e', width=2)
        ))
        
        # Add vertical lines for override hours
        for hour, price in zip(override_hours, override_prices):
            if hour <= results_df['hour'].max():
                fig.add_vline(
                    x=hour,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Price: {price:.4f}",
                    annotation_position="top",
                    opacity=0.7
                )
        
        fig.update_layout(
            xaxis_title="Hour",
            yaxis_title="Balance",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, width='stretch')

    with tab4:
        st.subheader("Slippage (Price Impact %)")
        st.caption("Slippage represents the percentage change in price due to each hourly swap.")
        
        if 'slippage_pct' in results_df.columns:
            # Filter out hour 0 (no swap happens at hour 0, so slippage is always 0)
            slippage_df = results_df[results_df['hour'] > 0].copy()
            
            if len(slippage_df) > 0:
                # Create plotly chart with override indicators
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=slippage_df['hour'],
                    y=slippage_df['slippage_pct'],
                    mode='lines',
                    name='Slippage (%)',
                    line=dict(color='#9467bd', width=2)
                ))
                
                # Add vertical lines for override hours (only if > 0)
                for hour, price in zip(override_hours, override_prices):
                    if hour > 0 and hour <= slippage_df['hour'].max():
                        fig.add_vline(
                            x=hour,
                            line_dash="dash",
                            line_color="red",
                            annotation_text=f"Price: {price:.4f}",
                            annotation_position="top",
                            opacity=0.7
                        )
                
                fig.update_layout(
                    xaxis_title="Hour",
                    yaxis_title="Slippage (%)",
                    hovermode='x unified',
                    height=400
                )
                st.plotly_chart(fig, width='stretch')
                
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