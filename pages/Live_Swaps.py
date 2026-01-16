import streamlit as st
import pandas as pd
import time
import sys
from pathlib import Path
import plotly.graph_objects as go
from datetime import datetime

# Add parent directory to path to import graphql module
sys.path.append(str(Path(__file__).parent.parent))
import graphql

st.set_page_config(
    page_title="Live Swap Monitor",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Live Swap Monitor")
st.markdown("Monitor real-time swap activity on Balancer pools")

# Sidebar configuration
st.sidebar.title("Pool Configuration")
st.sidebar.markdown("---")

# Pool address input
pool_address = st.sidebar.text_input(
    "Pool Address",
    value="0x3de27efa2f1aa663ae5d458857e731c129069f29",
    help="Enter the Balancer pool address to monitor"
)

# Fetch pool info
if pool_address:
    try:
        with st.spinner("Fetching pool information..."):
            pool_info = graphql.get_pool_by_address(pool_address)
        
        if pool_info:
            st.sidebar.success("✅ Pool found!")
            
            # Display pool info in sidebar
            with st.sidebar.container(border=True):
                st.subheader("Pool Details")
                st.caption(f"**Type:** {pool_info.get('poolType', 'N/A')}")
                st.caption(f"**Swap Fee:** {float(pool_info.get('swapFee', 0))*100:.2f}%")
                st.caption(f"**Total Liquidity:** ${float(pool_info.get('totalLiquidity', 0)):,.2f}")
                st.caption(f"**Total Volume:** ${float(pool_info.get('totalSwapVolume', 0)):,.2f}")
                
                st.markdown("**Tokens:**")
                for token in pool_info.get('tokens', []):
                    st.caption(f"• {token.get('symbol', 'N/A')} ({float(token.get('weight', 0))*100:.0f}%)")
                    st.caption(f"  Balance: {float(token.get('balance', 0)):,.2f}")
        else:
            st.sidebar.error("❌ Pool not found")
            pool_info = None
    except Exception as e:
        st.sidebar.error(f"❌ Error fetching pool: {str(e)}")
        pool_info = None
else:
    pool_info = None
    st.sidebar.warning("⚠️ Enter a pool address")

# Time range selector
st.sidebar.markdown("---")
st.sidebar.subheader("Time Range")
time_range = st.sidebar.selectbox(
    "Look back period",
    options=[
        ("Last 1 hour", 3600),
        ("Last 6 hours", 21600),
        ("Last 24 hours", 86400),
        ("Last 7 days", 604800),
        ("Last 30 days", 2592000),
    ],
    format_func=lambda x: x[0],
    index=2  # Default to 24 hours
)

# Auto-refresh toggle
st.sidebar.markdown("---")
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
refresh_interval = st.sidebar.slider(
    "Refresh interval (seconds)",
    min_value=5,
    max_value=60,
    value=10,
    step=5,
    disabled=not auto_refresh
)

# Manual refresh button
if st.sidebar.button("🔄 Refresh Now", use_container_width=True):
    st.rerun()

# Main content
if pool_info:
    pool_id = pool_info['id']
    
    # Calculate timestamp for lookback period
    lookback_seconds = time_range[1]
    since_timestamp = int(time.time()) - lookback_seconds
    
    # Fetch swaps
    try:
        with st.spinner(f"Fetching swaps for the last {time_range[0].lower()}..."):
            data = graphql.gql(graphql.SWAPS_QUERY, {"poolId": pool_id, "since": since_timestamp})
            swaps = data.get("swaps", [])
        
        if swaps:
            st.success(f"✅ Found {len(swaps)} swap(s) in the last {time_range[0].lower()}")
            
            # Process swaps into DataFrame
            swap_data = []
            for s in swaps:
                swap_data.append({
                    'timestamp': int(s['timestamp']),
                    'datetime': datetime.fromtimestamp(int(s['timestamp'])).strftime('%Y-%m-%d %H:%M:%S'),
                    'tokenIn': s['tokenIn'][-6:],  # Last 6 chars for brevity
                    'tokenOut': s['tokenOut'][-6:],
                    'amountIn': float(s['tokenAmountIn']),
                    'amountOut': float(s['tokenAmountOut']),
                    'valueUSD': float(s.get('valueUSD', 0)),
                    'tx': s['tx']
                })
            
            df = pd.DataFrame(swap_data).sort_values('timestamp', ascending=False)
            
            # Create tabs for different views
            tab1, tab2, tab3 = st.tabs(["📈 Overview", "📋 Swap Details", "📊 Analytics"])
            
            with tab1:
                # Key metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Swaps", len(df))
                
                with col2:
                    total_volume = df['valueUSD'].sum()
                    st.metric("Total Volume (USD)", f"${total_volume:,.2f}")
                
                with col3:
                    avg_swap = df['valueUSD'].mean() if len(df) > 0 else 0
                    st.metric("Avg Swap Size", f"${avg_swap:,.2f}")
                
                with col4:
                    if len(df) > 1:
                        time_diff = df['timestamp'].max() - df['timestamp'].min()
                        swaps_per_hour = (len(df) / time_diff * 3600) if time_diff > 0 else 0
                        st.metric("Swaps/Hour", f"{swaps_per_hour:.1f}")
                    else:
                        st.metric("Swaps/Hour", "N/A")
                
                st.markdown("---")
                
                # Volume over time chart
                st.subheader("Swap Volume Over Time")
                
                # Create time-based aggregation
                df_sorted = df.sort_values('timestamp')
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_sorted['datetime'],
                    y=df_sorted['valueUSD'],
                    mode='lines+markers',
                    name='Swap Value (USD)',
                    line=dict(color='#1f77b4', width=2),
                    marker=dict(size=6)
                ))
                
                fig.update_layout(
                    xaxis_title="Time",
                    yaxis_title="Value (USD)",
                    hovermode='x unified',
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Cumulative volume
                st.subheader("Cumulative Volume")
                df_sorted['cumulative_volume'] = df_sorted['valueUSD'].cumsum()
                
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=df_sorted['datetime'],
                    y=df_sorted['cumulative_volume'],
                    mode='lines',
                    name='Cumulative Volume (USD)',
                    line=dict(color='#2ca02c', width=2),
                    fill='tozeroy'
                ))
                
                fig2.update_layout(
                    xaxis_title="Time",
                    yaxis_title="Cumulative Volume (USD)",
                    hovermode='x unified',
                    height=300
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            with tab2:
                st.subheader("Recent Swaps")
                
                # Format display dataframe
                display_df = df.copy()
                display_df['Value (USD)'] = display_df['valueUSD'].apply(lambda x: f"${x:,.2f}")
                display_df['Amount In'] = display_df['amountIn'].apply(lambda x: f"{x:,.6f}")
                display_df['Amount Out'] = display_df['amountOut'].apply(lambda x: f"{x:,.6f}")
                display_df['Transaction'] = display_df['tx'].apply(
                    lambda x: f"[{x[:10]}...](https://etherscan.io/tx/{x})"
                )
                
                # Select columns for display
                display_columns = [
                    'datetime', 'tokenIn', 'tokenOut', 
                    'Amount In', 'Amount Out', 'Value (USD)', 'Transaction'
                ]
                
                st.dataframe(
                    display_df[display_columns].rename(columns={
                        'datetime': 'Time',
                        'tokenIn': 'Token In',
                        'tokenOut': 'Token Out'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"swaps_{pool_id}_{int(time.time())}.csv",
                    mime="text/csv"
                )
            
            with tab3:
                st.subheader("Analytics")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Token flow analysis
                    st.markdown("**Token Flow Distribution**")
                    
                    token_in_counts = df['tokenIn'].value_counts()
                    
                    fig3 = go.Figure(data=[go.Pie(
                        labels=[f"...{label}" for label in token_in_counts.index],
                        values=token_in_counts.values,
                        hole=.3
                    )])
                    fig3.update_layout(
                        title="Tokens Swapped In",
                        height=300
                    )
                    st.plotly_chart(fig3, use_container_width=True)
                
                with col2:
                    # Swap size distribution
                    st.markdown("**Swap Size Distribution**")
                    
                    fig4 = go.Figure(data=[go.Histogram(
                        x=df['valueUSD'],
                        nbinsx=20,
                        marker_color='#9467bd'
                    )])
                    fig4.update_layout(
                        title="Swap Value Distribution (USD)",
                        xaxis_title="Value (USD)",
                        yaxis_title="Count",
                        height=300
                    )
                    st.plotly_chart(fig4, use_container_width=True)
                
                # Top swaps
                st.markdown("**Top 10 Largest Swaps**")
                top_swaps = df.nlargest(10, 'valueUSD')[
                    ['datetime', 'tokenIn', 'tokenOut', 'valueUSD']
                ].copy()
                top_swaps['valueUSD'] = top_swaps['valueUSD'].apply(lambda x: f"${x:,.2f}")
                top_swaps = top_swaps.rename(columns={
                    'datetime': 'Time',
                    'tokenIn': 'Token In',
                    'tokenOut': 'Token Out',
                    'valueUSD': 'Value (USD)'
                })
                st.dataframe(top_swaps, use_container_width=True, hide_index=True)
            
        else:
            st.info(f"ℹ️ No swaps found in the last {time_range[0].lower()}. This pool might have low activity.")
            st.caption("Try selecting a longer time range or check a different pool address.")
    
    except Exception as e:
        st.error(f"❌ Error fetching swaps: {str(e)}")
        st.caption("Please check your GraphQL endpoint configuration in the .env file.")

else:
    st.info("👈 Enter a pool address in the sidebar to start monitoring swaps")

# Auto-refresh logic
if auto_refresh:
    st.caption(f"🔄 Auto-refreshing every {refresh_interval} seconds...")
    time.sleep(refresh_interval)
    st.rerun()

# Footer
st.markdown("---")
st.caption("💡 Tip: Enable auto-refresh to monitor swaps in real-time!")
