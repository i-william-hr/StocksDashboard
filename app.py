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
    initial_sidebar_state="collapsed"
)

PORTFOLIO_FILE = "portfolio.json"

# --- Security Configuration ---
AUTH_USER = "USER"
AUTH_PASS = "PASS"
AUTH_TOKEN = "TOKEN"

# --- Authentication Function ---
def check_authentication():
    if st.session_state.get("authenticated", False):
        return True
    
    query_params = st.query_params
    token = query_params.get("auth", None)
    
    if token == AUTH_TOKEN:
        st.session_state["authenticated"] = True
        return True

    st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔒 Restricted Access")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
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
def fetch_stock_name(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get('longName') or info.get('shortName') or ticker
    except:
        return ticker

@st.cache_data(ttl=300)
def get_live_data(tickers):
    if not tickers:
        return None
    return yf.download(tickers, period="6mo", group_by='ticker')

# --- Main Application ---
def main():
    if not check_authentication():
        st.stop()
    
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem; padding-bottom: 0rem; }
        </style>
    """, unsafe_allow_html=True)

    portfolio = load_portfolio()
    
    # --- Sidebar ---
    st.sidebar.title("💼 Portfolio")
    if st.sidebar.button("Logout", type="primary"):
        st.session_state["authenticated"] = False
        st.rerun()

    # --- ADD STOCK FORM ---
    with st.sidebar.form("add_stock_form"):
        st.write("### Add / Update Asset")
        ticker_input = st.text_input("Ticker (e.g. NVDA, XAGEUR=X)").upper().strip()
        amount_input = st.number_input("Shares/Units Held", min_value=0.0001, step=0.0001, format="%.4f")
        buy_date_input = st.date_input("Date Bought", value="today")
        st.write("---")
        manual_price = st.number_input("Manual Buy Price (Optional)", min_value=0.0, step=0.01)
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and ticker_input:
            name = fetch_stock_name(ticker_input)
            final_buy_price = 0.0
            
            if manual_price > 0:
                final_buy_price = manual_price
            else:
                try:
                    with st.spinner("Fetching historical price..."):
                        stock = yf.Ticker(ticker_input)
                        start_d = buy_date_input.strftime('%Y-%m-%d')
                        end_d = (buy_date_input + timedelta(days=5)).strftime('%Y-%m-%d')
                        hist = stock.history(start=start_d, end=end_d)
                        if not hist.empty:
                            final_buy_price = hist['Close'].iloc[0]
                        else:
                            st.sidebar.error("Could not find price history! Please enter 'Manual Buy Price'.")
                            st.stop()
                except Exception as e:
                    st.sidebar.error(f"Error fetching data: {e}. Use Manual Price.")
                    st.stop()

            portfolio[ticker_input] = {
                "shares": amount_input,
                "buy_date": buy_date_input.strftime('%Y-%m-%d'),
                "buy_price": final_buy_price,
                "name": name,
                "last_known_price": final_buy_price
            }
            save_portfolio(portfolio)
            st.sidebar.success(f"Added {name}!")
            st.rerun()

    if portfolio:
        st.sidebar.markdown("---")
        stock_to_remove = st.sidebar.selectbox("Select asset to remove", options=portfolio.keys())
        if st.sidebar.button("Remove Selected"):
            del portfolio[stock_to_remove]
            save_portfolio(portfolio)
            st.rerun()

    # --- Main Dashboard ---
    st.title("📈 Market Dashboard")

    if not portfolio:
        st.info("Portfolio empty. Add assets in the sidebar.")
        return

    tickers = list(portfolio.keys())
    live_data = get_live_data(tickers)
    
    portfolio_rows = []
    total_current_value = 0.0
    total_cost_basis = 0.0
    data_updated = False 
    
    for ticker, info in portfolio.items():
        current_price = None
        
        # 1. Fetch Live
        try:
            if live_data is not None:
                try:
                    stock_df = live_data[ticker]
                except KeyError:
                    stock_df = live_data
                
                if 'Close' in stock_df.columns and not stock_df['Close'].isna().all():
                    price_candidate = stock_df['Close'].iloc[-1]
                    if isinstance(price_candidate, pd.Series): 
                        price_candidate = price_candidate.item()
                    
                    if pd.notna(price_candidate) and price_candidate > 0:
                        current_price = price_candidate
                        if info.get('last_known_price') != current_price:
                            portfolio[ticker]['last_known_price'] = current_price
                            data_updated = True
        except Exception:
            pass

        # 2. Fallback
        if current_price is None or pd.isna(current_price):
            current_price = info.get('last_known_price', 0.0)
        
        # Calculate
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
            "Gain/Loss": gain_loss_amt,
            "Gain %": gain_loss_pct
        })

    if data_updated:
        save_portfolio(portfolio)

    if not portfolio_rows:
        st.warning("No data available.")
        return

    df = pd.DataFrame(portfolio_rows)
    
    # --- Metrics Section (UPDATED) ---
    total_gain_loss = total_current_value - total_cost_basis
    total_gain_pct = (total_gain_loss / total_cost_basis) * 100 if total_cost_basis > 0 else 0
    
    # Identify Winners/Losers
    top_abs = df.loc[df['Gain/Loss'].idxmax()]  # Max Gain in Euros
    top_pct = df.loc[df['Gain %'].idxmax()]     # Max Gain in %
    worst_abs = df.loc[df['Gain/Loss'].idxmin()] # Max Loss in Euros

    # Layout: 5 Columns to fit all metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    # 1. Net Worth
    col1.metric("Net Worth", f"€{total_current_value:,.2f}")
    
    # 2. Total Gain
    col2.metric("Total Gain/Loss", f"€{total_gain_loss:,.2f}", f"{total_gain_pct:+.2f}%")
    
    # 3. Best Asset € (Euros + %)
    col3.metric(
        "Best Asset €", 
        top_abs['Ticker'], 
        f"€{top_abs['Gain/Loss']:,.2f} ({top_abs['Gain %']:+.2f}%)"
    )
    
    # 4. Best Asset % (New Column!)
    col4.metric(
        "Best Asset %", 
        top_pct['Ticker'], 
        f"{top_pct['Gain %']:+.2f}% (€{top_pct['Gain/Loss']:,.2f})"
    )

    # 5. Worst Asset € (Euros + %)
    col5.metric(
        "Worst Asset €", 
        worst_abs['Ticker'], 
        f"€{worst_abs['Gain/Loss']:,.2f} ({worst_abs['Gain %']:+.2f}%)"
    )

    st.markdown("---")

    # --- Charts ---
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Allocation")
        fig_pie = px.pie(df, values='Current Value', names='Ticker', hole=0.4)
        fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with c2:
        st.subheader("Gains")
        df['Color'] = df['Gain/Loss'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
        color_map = {'Profit': '#00CC96', 'Loss': '#EF553B'}
        fig_bar = px.bar(df, x='Ticker', y='Gain/Loss', color='Color', color_discrete_map=color_map)
        fig_bar.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("Details")
    st.dataframe(
        df[['Ticker', 'Shares', 'Buy Price', 'Current Price', 'Gain/Loss', 'Gain %']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Buy Price": st.column_config.NumberColumn(format="€%.2f"),
            "Current Price": st.column_config.NumberColumn(format="€%.2f"),
            "Gain/Loss": st.column_config.NumberColumn(format="€%.2f"),
            "Gain %": st.column_config.NumberColumn(format="%.2f%%"),
        }
    )
    
    st.subheader("Performance (6 Mo)")
    history_df = pd.DataFrame()
    for ticker in tickers:
        qty = portfolio[ticker]['shares']
        try:
            stock_hist = live_data[ticker]
        except:
            stock_hist = live_data
        
        if stock_hist is not None and 'Close' in stock_hist.columns:
             val_series = stock_hist['Close'] * qty
             if history_df.empty:
                 history_df = val_series.to_frame(name="Total Value")
             else:
                 history_df["Total Value"] = history_df["Total Value"].add(val_series, fill_value=0)

    if not history_df.empty:
        fig_line = px.line(history_df, y="Total Value")
        fig_line.update_traces(line_color='#636EFA', line_width=3)
        fig_line.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.caption("Live historical data temporarily unavailable.")

if __name__ == "__main__":
    main()
