import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import json

st.set_page_config(layout="wide", page_title="FAF Food Flows Dashboard")

st.markdown("""
<style>
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    .block-container { padding: 0; margin: 0; }
    .st-emotion-cache-1y4p8pa { padding: 0; }
</style>
""", unsafe_allow_html=True)

FAF_FILES = {
    "Live Animals/Fish": "cleaned_sctg_2_1.xlsx",
    "Cereal Grains": "cleaned_sctg_2_2.xlsx",
    "Other Ag products.": "cleaned_sctg_2_3.xlsx",
    "Animal Feed": "cleaned_sctg_2_4.xlsx",
    "Meat/Seafood": "cleaned_sctg_2_5.xlsx",
    "Milled Grain Prods.": "cleaned_sctg_2_6.xlsx",
    "Other Foodstuffs": "cleaned_sctg_2_7.xlsx"
}

@st.cache_data
def load_sctg_data(file_name):
    df = pd.read_excel(f"./files/FAF_with_CENTROIDS/{file_name}")
    df['dms_orig'] = df['dms_orig'].astype(str).str.zfill(3)
    df['dms_dest'] = df['dms_dest'].astype(str).str.zfill(3)
    return df

@st.cache_data
def load_zone_metadata():
    df = pd.read_excel("./files/FAF5_metadata.xlsx", sheet_name="FAF Zone (Domestic)")
    df.columns = df.columns.str.strip()  # Remove leading/trailing spaces
    df['Numeric Label'] = df['Numeric Label'].astype(str).str.zfill(3)  # Ensure codes are 3-digit strings

    df = df.rename(columns={
        "Numeric Label": "FAF_Zone",
        "Short Description": "state"
    })

    return df[['FAF_Zone', 'state']]

@st.cache_data
def load_faf_boundaries():
    gdf = gpd.read_file("./files/2017_CFS_Metro_Areas_with_FAF/2017_CFS_Metro_Areas_with_FAF.shp")
    gdf['FAF_Zone'] = gdf['FAF_Zone'].astype(str).str.zfill(3)
    gdf = gdf.merge(load_zone_metadata(), on="FAF_Zone", how="left")
    gdf = gdf.to_crs("EPSG:4326")
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.01, preserve_topology=True)
    return json.loads(gdf.to_json())

def convert_sctg_to_trip(sctg_df):
    return pd.DataFrame({
        "coordinates": [
            [[ox, oy], [dx, dy]]
            for ox, oy, dx, dy in zip(
                sctg_df["centroid_x_orig"], sctg_df["centroid_y_orig"],
                sctg_df["centroid_x_dest"], sctg_df["centroid_y_dest"]
            )
        ],
        "timestamps": [[0, 2]] * len(sctg_df),
        "orig_dms": sctg_df["dms_orig"].tolist(),
        "dest_dms": sctg_df["dms_dest"].tolist()
    })

# Load data
zone_meta = load_zone_metadata()
boundary_geojson = load_faf_boundaries()

# Layout
col1, col2 = st.columns([1, 4])

with col1:
    st.markdown("### Settings")

    selected_category = st.selectbox("Select Food Category", options=list(FAF_FILES.keys()))
    sctg_df = load_sctg_data(FAF_FILES[selected_category])

    orig_zones = sorted(sctg_df['dms_orig'].unique())
    orig_display = [
        f"{zone} - {zone_meta.loc[zone_meta['FAF_Zone'] == zone, 'state'].values[0]}"
        if zone in zone_meta['FAF_Zone'].values else zone
        for zone in orig_zones
    ]

    selected_zone_label = st.selectbox("Select FAF Origin Zone", options=orig_display)
    selected_faf_zone = selected_zone_label.split(" - ")[0]

    # Filter to selected origin
    filtered_df = sctg_df[sctg_df['dms_orig'] == selected_faf_zone]

    # Destination filter
    dest_zones = sorted(filtered_df['dms_dest'].unique())
    dest_display = [
        f"{zone} - {zone_meta.loc[zone_meta['FAF_Zone'] == zone, 'state'].values[0]}"
        if zone in zone_meta['FAF_Zone'].values else zone
        for zone in dest_zones
    ]
    selected_dest_label = st.selectbox("Select Destination Zone", options=["All"] + dest_display)

    if selected_dest_label != "All":
        selected_dest_zone = selected_dest_label.split(" - ")[0]
        filtered_df = filtered_df[filtered_df['dms_dest'] == selected_dest_zone]

    st.markdown(f"### Displaying trips from **{selected_zone_label}**")

    # === Summary statistics ===
    num_trips = len(filtered_df)
    total_tons = filtered_df['tons_2017'].sum()
    total_value = filtered_df['value_2017'].sum()
    total_tmiles = filtered_df['tmiles_2017'].sum()

    st.markdown("### Trip Summary Statistics")
    st.markdown(f"- **Number of trips:** {num_trips:,}")
    st.markdown(f"- **Total tons shipped:** {total_tons:,.1f} thousand tons")
    st.markdown(f"- **Total value shipped:** ${total_value:,.1f} million")
    st.markdown(f"- **Total ton-miles:** {total_tmiles:,.1f} million ton-miles")

    # Top 5 destinations by tons shipped
    top_dests = (
        filtered_df.groupby('dms_dest')['tons_2017']
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .reset_index()
    )

    # Map destination zones to state names for display
    top_dests['state'] = top_dests['dms_dest'].map(
        lambda z: zone_meta.loc[zone_meta['FAF_Zone'] == z, 'state'].values[0]
        if z in zone_meta['FAF_Zone'].values else z
    )

    st.markdown("### Top 5 Destination Zones by Tons Shipped")
    st.table(
        top_dests.rename(columns={'dms_dest': 'Destination Zone', 'tons_2017': 'Tons Shipped', 'state': 'State'})
    )


# Create layers
trip_df = convert_sctg_to_trip(filtered_df)

boundary_layer = pdk.Layer(
    "GeoJsonLayer",
    boundary_geojson,
    stroked=True,
    filled=True,
    get_fill_color=[0, 0, 0, 20],
    get_line_color=[128, 128, 128],
    line_width_min_pixels=1.5,
    pickable=True,
    auto_highlight=True,
    highlight_color=[255, 255, 0, 100]
)

layer = pdk.Layer(
    "ArcLayer",
    trip_df,
    get_source_position="coordinates[0]",
    get_target_position="coordinates[1]",
    get_width=2,
    get_tilt=15,
    get_source_color=[0, 200, 255],
    get_target_color=[255, 100, 100],
    tooltip=True
)

tooltip = {
    "html": "<b>FAF Zone:</b> {FAF_Zone}<br/><b>State:</b> {state}",
    "style": {
        "backgroundColor": "steelblue",
        "color": "white"
    }
}

view_state = pdk.ViewState(latitude=39.8283, longitude=-98.5795, zoom=4, bearing=0, pitch=45)

with col2:
    st.pydeck_chart(
        pdk.Deck(
            layers=[boundary_layer, layer],
            initial_view_state=view_state,
            tooltip=tooltip
        ),
        use_container_width=True,
        height=900
    )
