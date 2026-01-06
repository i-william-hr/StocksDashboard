import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime, timedelta

# --- Configuration & Setup ---
st.set_page_config(
    page_title="Stock Dashboard Pro",
    layout="wide",
    initial_sidebar_state="collapsed"  # Mobile friendly: Collapsed by default
)

PORTFOLIO_FILE = "portfolio.json"

# --- Security Configuration ---
AUTH_USER = "USER"
AUTH_PASS = "PASS"
AUTH_TOKEN = "TOKEN"

# --- Authentication Function ---
def check_authentication():
    """
    Returns True if the user is authenticated (via session or URL), 
    False otherwise.
    """
    if st.session_state.get("authenticated", False):
        return True

    # Check for Magic URL Parameter
    query_params = st.query_params
    token = query_params.get("auth", None)
    
    if token == AUTH_TOKEN:
        st.session_state["authenticated"] = True
        return True

    # Show Login Form if not authenticated
    st.markdown("""
        <style>
            .block-container { padding-top: 2rem; }
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔒 Restricted Access")
        st.write("Please log in to view the dashboard.")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                if username == AUTH_USER and password == AUTH_PASS:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect Username or Password")
    
    return False

# --- Data Persistence ---
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    return {}

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f)

# --- Helper Functions ---
def fetch_stock_info(ticker, buy_date):
    try:
        stock = yf.Ticker(ticker)
        # Fetch minimal info for name
        info = stock.info
        long_name = info.get('longName') or info.get('shortName') or ticker
        
        # Calculate search window for price (buy date + 3 days buffer for weekends)
        start_date_str = buy_date.strftime('%Y-%m-%d')
        end_date = buy_date + timedelta(days=3) 
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        history = stock.history(start=start_date_str, end=end_date_str)
        
        if history.empty:
            return None, None, "No price data found for this date."
            
        buy_price = history['Close'].iloc[0]
        return long_name, buy_price, None
    except Exception as e:
        return None, None, str(e)

@st.cache_data(ttl=300)
def get_live_data(tickers):
    if not tickers:
        return None
    # Download data
    data = yf.download(tickers, period="6mo", group_by='ticker')
    return data

# --- Main Application ---
def main():
    # 1. Security Check
    if not check_authentication():
        st.stop()
    
    # 2. CSS Optimization for Mobile (Removes top padding)
    st.markdown("""
        <style>
            .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }
        </style>
    """, unsafe_allow_html=True)

    portfolio = load_portfolio()
    
    # --- Sidebar ---
    st.sidebar.title("💼 Portfolio")
    
    if st.sidebar.button("Logout", type="primary"):
        st.session_state["authenticated"] = False
        st.rerun()

    with st.sidebar.form("add_stock_form"):
        st.write("### Add / Update Stock")
        ticker_input = st.text_input("Ticker (e.g. NVDA, AUM5.DE)").upper().strip()
        amount_input = st.number_input("Shares Held", min_value=0.01, step=0.01)
        buy_date_input = st.date_input("Date Bought", value="today", max_value=datetime.today())
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and ticker_input:
            with st.spinner(f"Fetching data for {ticker_input}..."):
                name, buy_price, error = fetch_stock_info(ticker_input, buy_date_input)
                
                if error:
                    st.sidebar.error(f"Error: {error}")
                else:
                    portfolio[ticker_input] = {
                        "shares": amount_input,
                        "buy_date": buy_date_input.strftime('%Y-%m-%d'),
                        "buy_price": buy_price,
                        "name": name
                    }
                    save_portfolio(portfolio)
                    st.sidebar.success(f"Added {name}")
                    st.rerun()

    if portfolio:
        st.sidebar.markdown("---")
        st.sidebar.write("### Remove Stock")
        stock_to_remove = st.sidebar.selectbox("Select stock", options=portfolio.keys())
        if st.sidebar.button("Remove Selected"):
            del portfolio[stock_to_remove]
            save_portfolio(portfolio)
            st.rerun()

    # --- Main Content ---
    st.title("📈 Market Dashboard")

    if not portfolio:
        st.info("Your portfolio is empty. Open the sidebar (top-left) to add stocks.")
        return

    tickers = list(portfolio.keys())
    live_data = get_live_data(tickers)
    
    portfolio_rows = []
    total_current_value = 0.0
    total_cost_basis = 0.0
    
    # Process Data
    for ticker, info in portfolio.items():
        # Handle single vs multi-index data structure from yfinance
        try:
            stock_df = live_data[ticker]
        except KeyError:
            stock_df = live_data
            
        if 'Close' not in stock_df.columns:
            continue
            
        current_price = stock_df['Close'].iloc[-1]
        if isinstance(current_price, pd.Series): current_price = current_price.item()

        shares = info['shares']
        buy_price = info['buy_price']
        
        current_value = current_price * shares
        cost_basis = buy_price * shares
        gain_loss_amt = current_value - cost_basis
        gain_loss_pct = (gain_loss_amt / cost_basis) * 100 if cost_basis > 0 else 0
        
        total_current_value += current_value
        total_cost_basis += cost_basis
        
        portfolio_rows.append({
            "Ticker": ticker,
            "Name": info['name'],
            "Shares": shares,
            "Buy Date": info['buy_date'],
            "Buy Price": buy_price,
            "Current Price": current_price,
            "Current Value": current_value,
            "Gain/Loss ($)": gain_loss_amt,
            "Gain/Loss (%)": gain_loss_pct
        })

    if not portfolio_rows:
        st.warning("Data unavailable. Please check your internet connection or ticker symbols.")
        return

    df = pd.DataFrame(portfolio_rows)
    
    # Calculate Totals
    total_gain_loss = total_current_value - total_cost_basis
    total_gain_pct = (total_gain_loss / total_cost_basis) * 100 if total_cost_basis > 0 else 0
    
    # --- Top Metrics Row ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net Worth", f"${total_current_value:,.2f}")
    col2.metric("Total Gain/Loss", f"${total_gain_loss:,.2f}", f"{total_gain_pct:.2f}%")
    
    top_performer = df.loc[df['Gain/Loss ($)'].idxmax()]
    col3.metric("Best Performer", top_performer['Ticker'], f"${top_performer['Gain/Loss ($)']:,.2f}")
    
    worst_performer = df.loc[df['Gain/Loss ($)'].idxmin()]
    col4.metric("Worst Performer", worst_performer['Ticker'], f"${worst_performer['Gain/Loss ($)']:,.2f}")

    st.markdown("---")

    # --- Charts Area ---
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("Allocation")
        fig_pie = px.pie(df, values='Current Value', names='Ticker', hole=0.4, hover_data=['Name'])
        # Minimal margins for mobile
        fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with c2:
        st.subheader("Gain/Loss by Stock")
        df['Color'] = df['Gain/Loss ($)'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
        color_map = {'Profit': '#00CC96', 'Loss': '#EF553B'}
        fig_bar = px.bar(df, x='Ticker', y='Gain/Loss ($)', color='Color', color_discrete_map=color_map, hover_data=['Name'])
        fig_bar.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- Detailed Table ---
    st.subheader("Holdings Details")
    st.dataframe(
        df[['Ticker', 'Name', 'Buy Date', 'Shares', 'Buy Price', 'Current Price', 'Gain/Loss ($)', 'Gain/Loss (%)']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Buy Price": st.column_config.NumberColumn(format="$%.2f"),
            "Current Price": st.column_config.NumberColumn(format="$%.2f"),
            "Gain/Loss ($)": st.column_config.NumberColumn(format="$%.2f"),
            "Gain/Loss (%)": st.column_config.NumberColumn(format="%.2f%%"),
        }
    )

    # --- Historical Graph ---
    st.subheader("Portfolio Performance (6 Mo)")
    history_df = pd.DataFrame()
    for ticker in tickers:
        qty = portfolio[ticker]['shares']
        try:
            stock_hist = live_data[ticker]
        except KeyError:
            stock_hist = live_data
        if 'Close' in stock_hist.columns:
            val_series = stock_hist['Close'] * qty
            if history_df.empty:
                history_df = val_series.to_frame(name="Total Value")
            else:
                history_df["Total Value"] = history_df["Total Value"].add(val_series, fill_value=0)

    fig_line = px.line(history_df, y="Total Value")
    fig_line.update_traces(line_color='#636EFA', line_width=3)
    fig_line.update_layout(margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_line, use_container_width=True)

if __name__ == "__main__":
    main()
