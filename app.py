###############   streamlit run app.py to ################# TO RUN THE CODE

import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk

# Page configurations
st.set_page_config(
    layout="wide", # using the entire width of the browser
    page_title="FAF Food Flows Dashboard" # the title of the browser tab
    )

# apply custom css to remove margins and make the map full-screen
st.markdown(
    """
    <style>
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
        .block-container { padding: 0; margin: 0; }
        .st-emotion-cache-1y4p8pa { padding: 0; }
    </style>
    """,
    unsafe_allow_html=True
)

# load the sctg dataset
@st.cache_data
def load_sctg_data():
    sctg_2_1 = pd.read_excel("./files/sctg_2_processed_files/cleaned_sctg_2_1.xlsx")
    sctg_2_1['dms_orig'] = sctg_2_1['dms_orig'].astype(int).apply(lambda x: f"{x:03d}")
    sctg_2_1['dms_dest'] = sctg_2_1['dms_dest'].astype(int).apply(lambda x: f"{x:03d}")
    return sctg_2_1

# load and process the shapefile
@st.cache_data
def load_shapefile():
    shp = gpd.read_file("./files/2017_CFS_Metro_Areas_with_FAF/2017_CFS_Metro_Areas_with_FAF.shp")
    shp['centroid'] = shp['geometry'].centroid
    return shp[['FAF_Zone', 'centroid']]

sctg_2_1 = load_sctg_data()
shp = load_shapefile()

# merge data to get centroid locations
sctg_2_1['dms_orig_centroid'] = sctg_2_1['dms_orig'].map(shp.set_index('FAF_Zone')['centroid'])
sctg_2_1['dms_dest_centroid'] = sctg_2_1['dms_dest'].map(shp.set_index('FAF_Zone')['centroid'])

# function to convert filtered sctg data into trip format
def convert_sctg_to_trip(sctg_df):
    return pd.DataFrame({
        "coordinates": [
            [[point.x, point.y], [dest.x, dest.y]]
            for point, dest in zip(sctg_df["dms_orig_centroid"], sctg_df["dms_dest_centroid"])
        ],
        "timestamps": [[0, 2]] * len(sctg_df),
        "orig_dms": sctg_df["dms_orig"].tolist(),
        "dest_dms": sctg_df["dms_dest"].tolist()
    })

# create two columns: one for settings, one for the map
col1, col2 = st.columns([1, 4])

with col1:
    st.markdown("### Settings")
    sctg_file = st.selectbox(
        "Select Food Category",
        options=["Live Animals", "Cereal Grains", "Animal Feed"]

    )

    selected_faf_zone = st.selectbox(
        "Select FAF Zone",
        options=sctg_2_1['dms_orig'].unique()
    )
    
    selected_layer = st.radio(
        "Select Layer Type",
        options=["TripsLayer", "ArcLayer"],
        index=0
    )
    
    st.write(f"Displaying **{selected_layer}** for trips originating from FAF Zone: `{selected_faf_zone}`")

# filter the dataset based on the selected faf zone
filtered_df = sctg_2_1[sctg_2_1['dms_orig'] == selected_faf_zone]

# convert the filtered data into trip format
trip_df = convert_sctg_to_trip(filtered_df)

# set up the visualization layer based on user selection
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

# set up the initial view state for the map
view_state = pdk.ViewState(
    latitude=39.8283, longitude=-98.5795, zoom=4, bearing=0, pitch=45
)

# render the map in the second column (full screen minus settings)
with col2:
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state), use_container_width=True, height=900)
