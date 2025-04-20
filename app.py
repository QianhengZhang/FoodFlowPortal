import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import json

st.set_page_config(layout="wide", page_title="FAF Food Flows Dashboard")

# Custom CSS to go fullscreen
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
    df['Numeric Label'] = df['Numeric Label'].astype(str).str.zfill(3)
    df = df.rename(columns={"Numeric Label": "FAF_Zone", "Short Description": "zone_name"})
    return df[['FAF_Zone', 'zone_name']]

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

boundary_geojson = load_faf_boundaries()

col1, col2 = st.columns([1, 4])

with col1:
    st.markdown("### Settings")

    selected_category = st.selectbox("Select Food Category", options=list(FAF_FILES.keys()))
    sctg_df = load_sctg_data(FAF_FILES[selected_category])

    selected_faf_zone = st.selectbox("Select FAF Zone", options=sorted(sctg_df['dms_orig'].unique()))
    selected_layer = st.radio("Select Layer Type", options=["TripsLayer", "ArcLayer"], index=0)

    st.write(f"Displaying **{selected_layer}** for trips originating from FAF Zone: `{selected_faf_zone}`")

filtered_df = sctg_df[sctg_df['dms_orig'] == selected_faf_zone]
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

if selected_layer == "TripsLayer":
    layer = pdk.Layer(
        "TripsLayer",
        trip_df,
        get_path="coordinates",
        get_timestamps="timestamps",
        get_color=[255, 125, 0],
        opacity=0.6,
        width_min_pixels=2,
        rounded=True,
        trail_length=150,
        current_time=2,
        get_tooltip="[orig_dms, dest_dms]",
    )
else:
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
    "html": "<b>FAF Zone:</b> {FAF_Zone}<br/><b>Name:</b> {zone_name}",
    "style": {
        "backgroundColor": "steelblue",
        "color": "white"
    }
}

view_state = pdk.ViewState(latitude=39.8283, longitude=-98.5795, zoom=4, bearing=0, pitch=45)

with col2:
    st.pydeck_chart(
        pdk.Deck(
            layers=[boundary_layer, layer],  # You could switch this to [boundary_layer, layer] if needed
            initial_view_state=view_state,
            tooltip=tooltip
        ),
        use_container_width=True,
        height=900
    )

