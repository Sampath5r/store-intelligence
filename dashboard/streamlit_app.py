import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px

# =========================================
# PAGE CONFIG
# =========================================
st.set_page_config(
    page_title="Store Intelligence Dashboard",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================
# CUSTOM CSS
# =========================================
st.markdown("""
<style>

/* Main App Background */
.stApp {
    background: linear-gradient(
        135deg,
        #0f172a,
        #111827,
        #1e293b
    );
    color: white;
}

/* Remove white blocks */
[data-testid="stAppViewContainer"] {
    background: transparent;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #111827;
    border-right: 1px solid #374151;
}

/* Main container */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* Metric cards */
.metric-card {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 18px;
    padding: 24px;
    text-align: center;
    box-shadow: 0px 8px 24px rgba(0,0,0,0.4);
    transition: 0.3s ease;
}

.metric-card:hover {
    transform: translateY(-4px);
    box-shadow: 0px 12px 30px rgba(0,0,0,0.6);
}

/* KPI Title */
.metric-title {
    font-size: 16px;
    color: #9CA3AF;
    margin-bottom: 10px;
}

/* KPI Value */
.metric-value {
    font-size: 34px;
    font-weight: bold;
    color: #F9FAFB;
}

/* Headers */
h1, h2, h3 {
    color: #F9FAFB !important;
}

/* Table Styling */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}

/* Buttons */
.stButton>button {
    border-radius: 10px;
    background: linear-gradient(90deg, #2563EB, #7C3AED);
    color: white;
    border: none;
}

/* Success box */
.stAlert {
    border-radius: 12px;
}

</style>
""", unsafe_allow_html=True)

# =========================================
# HEADER
# =========================================
st.title("🛍️ Store Intelligence Dashboard")
st.caption("AI-Powered Retail CCTV Analytics Platform")

# =========================================
# LOAD DATA
# =========================================
DATA_PATH = "data/analytics/summary.json"

if not os.path.exists(DATA_PATH):
    st.error("summary.json not found. Run analytics first.")
    st.stop()

with open(DATA_PATH, "r") as f:
    data = json.load(f)

summary = data.get("summary", [])

if not summary:
    st.warning("No analytics data available.")
    st.stop()

# =========================================
# DATAFRAME
# =========================================
df = pd.DataFrame(summary)

# =========================================
# CAMERA NAME MAPPING
# =========================================
camera_map = {
    "floor_camera1_events.json": "Floor Camera 1",
    "floor_camera2_events.json": "Floor Camera",
    "billing_camera_events.json": "Billing Camera",
    "entry_camera_events.json": "Entry Camera",
    "storage_area_events.json": "Storage Area"
}

df["camera_display"] = df["camera"].apply(
    lambda x: camera_map.get(x, x)
)

# =========================================
# SIDEBAR
# =========================================
st.sidebar.title("📌 Navigation")

selected_camera = st.sidebar.selectbox(
    "Select Camera",
    ["All Cameras"] + list(df["camera_display"].unique())
)

if selected_camera != "All Cameras":
    filtered_df = df[df["camera_display"] == selected_camera]
else:
    filtered_df = df

# =========================================
# KPI CALCULATIONS
# =========================================
total_customers = filtered_df["total_unique_people"].sum()
active_cameras = filtered_df["camera_display"].nunique()

top_camera_row = filtered_df.loc[
    filtered_df["total_unique_people"].idxmax()
]

top_camera = top_camera_row["camera_display"]
top_visitors = top_camera_row["total_unique_people"]

# =========================================
# KPI CARDS
# =========================================
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">👥 Total Visitors</div>
        <div class="metric-value">{int(total_customers)}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">📷 Active Cameras</div>
        <div class="metric-value">{active_cameras}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">🔥 Top Zone</div>
        <div class="metric-value">{top_camera}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# =========================================
# BAR CHART
# =========================================
st.subheader("📊 Visitor Distribution")

bar_fig = px.bar(
    filtered_df,
    x="camera_display",
    y="total_unique_people",
    text="total_unique_people",
    color="total_unique_people",
    template="plotly_dark",
    title="Visitors Per Camera"
)

bar_fig.update_layout(
    xaxis_title="Camera",
    yaxis_title="Visitors",
    height=500
)

st.plotly_chart(bar_fig, use_container_width=True)

# =========================================
# PIE CHART
# =========================================
st.subheader("🥧 Traffic Share")

pie_fig = px.pie(
    filtered_df,
    names="camera_display",
    values="total_unique_people",
    template="plotly_dark",
    hole=0.4
)

pie_fig.update_layout(height=500)

st.plotly_chart(pie_fig, use_container_width=True)

# =========================================
# ANALYTICS TABLE
# =========================================
st.subheader("📋 Detailed Analytics")

display_df = filtered_df[[
    "camera_display",
    "total_unique_people"
]].rename(columns={
    "camera_display": "Camera",
    "total_unique_people": "Visitors"
})

st.dataframe(display_df, use_container_width=True)

# =========================================
# AI INSIGHTS
# =========================================
st.subheader("🧠 AI Insights")

st.info(f"""
✅ Total Footfall: {int(total_customers)} visitors

✅ Most Active Zone: {top_camera}

✅ Peak Activity: {top_visitors} visitors

✅ Monitoring Coverage: {active_cameras} active cameras
""")

# =========================================
# FOOTER
# =========================================
st.markdown("---")
st.caption("🚀 Powered by YOLOv8 + ByteTrack + FastAPI + Streamlit")
st.caption("@Sampathrr")