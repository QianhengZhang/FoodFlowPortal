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
    .st-emotion-cache-1cn49yv {
        padding-left: 20px !important;
    }
</style>
""", unsafe_allow_html=True)


FAF_FILES = {
    "Live Animals/Fish": "predicted_sctg_1.csv",
    "Cereal Grains": "predicted_sctg_2.csv",
    "Other Ag products.": "predicted_sctg_3.csv",
    "Animal Feed": "predicted_sctg_4.csv",
    "Meat/Seafood": "predicted_sctg_5.csv",
    "Milled Grain Prods.": "predicted_sctg_6.csv",
    "Other Foodstuffs": "predicted_sctg_7.csv"
}

@st.cache_data
def load_sctg_data(file_name):
    df = pd.read_csv(f"./cleaned_data/{file_name}")
    df['origin'] = df['origin'].astype(str).str.zfill(5)
    df['dest'] = df['dest'].astype(str).str.zfill(5)
    df = df[df['exist_prob'] > 0.5]
    df = df[df['predicted_value_original'] > 0]
    return df

@st.cache_data
def load_county_metadata():
    #df = pd.read_excel("./files/FAF5_metadata.xlsx", sheet_name="FAF Zone (Domestic)")
    df = pd.read_csv("cleaned_data\state_and_county_fips_master.csv")
    #df.columns = df.columns.str.strip()  # Remove leading/trailing spaces
    df['fips'] = df['fips'].astype(str).str.zfill(5)  # Ensure codes are 3-digit strings

    df = df.rename(columns={
        "fips": "FIPS",
        "name": "County",
        'state': 'State'
    })

    return df[['FIPS', 'County', 'State']]

@st.cache_data
def load_county_boundaries():
    gdf = gpd.read_file("data\shapefiles\cb_2017_us_county_500k\cb_2017_us_county_500k.shp")
    gdf['GEOID'] = gdf['GEOID'].astype(str).str.zfill(5)
    gdf = gdf.rename(columns={'GEOID': 'FIPS'})
    gdf = gdf.merge(load_county_metadata(), on="FIPS", how="left")
    gdf = gdf.to_crs("EPSG:4326")
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.01, preserve_topology=True)
    return json.loads(gdf.to_json())

def convert_sctg_to_trip(sctg_df):
    return pd.DataFrame({
        "coordinates": [
            [[ox, oy], [dx, dy]]
            for ox, oy, dx, dy in zip(
                sctg_df["origin_x"], sctg_df["origin_y"],
                sctg_df["dest_x"], sctg_df["dest_y"]
            )
        ],
        "timestamps": [[0, 2]] * len(sctg_df),
        "orig_dms": sctg_df["origin"].tolist(),
        "dest_dms": sctg_df["dest"].tolist()
    })

# Load data
county_meta = load_county_metadata()
boundary_geojson = load_county_boundaries()

# Layout
col1, col2 = st.columns([1, 3])

with col1:
    st.markdown("# GNN Food Flows")
    st.markdown("### Settings")

    selected_category = st.selectbox("Select Food Category", options=list(FAF_FILES.keys()))
    sctg_df = load_sctg_data(FAF_FILES[selected_category])

    orig_counties = sorted(sctg_df['origin'].unique())
    orig_display = [
        f"{county} - {county_meta.loc[county_meta['FIPS'] == county, 'County'].values[0]} - {county_meta.loc[county_meta['FIPS'] == county, 'State'].values[0]}"
        if county in county_meta['FIPS'].values else county
        for county in orig_counties
    ]

    selected_county_label = st.selectbox("Select Origin County", options=orig_display, index=orig_display.index("06037 - Los Angeles County - CA"))
    selected_county = selected_county_label.split(" - ")[0]

    # Filter to selected origin
    filtered_df = sctg_df[sctg_df['origin'] == selected_county]

    # Destination filter
    dest_counties = sorted(filtered_df['dest'].unique())
    dest_display = [
        f"{county} - {county_meta.loc[county_meta['FIPS'] == county, 'County'].values[0]} - {county_meta.loc[county_meta['FIPS'] == county, 'State'].values[0]}"
        if county in county_meta['FIPS'].values else county
        for county in dest_counties
    ]
    selected_dest_label = st.selectbox("Select Destination County", options=["All"] + dest_display)

    if selected_dest_label != "All":
        selected_dest_zone = selected_dest_label.split(" - ")[0]
        filtered_df = filtered_df[filtered_df['dest'] == selected_dest_zone]

    st.markdown(f"### Displaying trips from **{selected_county_label}**")

    # === Summary statistics ===
    num_trips = len(filtered_df)
    total_tons = filtered_df['predicted_value_original'].sum()
    # total_value = filtered_df['value_2017'].sum()
    # total_tmiles = filtered_df['tmiles_2017'].sum()

    st.markdown("### Trip Summary Statistics")
    st.markdown(f"- **Number of trips:** {num_trips:,}")
    st.markdown(f"- **Total tons shipped:** {total_tons:,.1f} thousand tons")
    # st.markdown(f"- **Total value shipped:** ${total_value:,.1f} million")
    # st.markdown(f"- **Total ton-miles:** {total_tmiles:,.1f} million ton-miles")

    # Top 5 destinations by tons shipped
    top_dests = (
        filtered_df.groupby('dest')['predicted_value_original']
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .reset_index()
    )

    # Map destination zones to state names for display
    top_dests['state'] = top_dests['dest'].map(
        lambda z: county_meta.loc[county_meta['FIPS'] == z, 'State'].values[0]
        if z in county_meta['FIPS'].values else z
    )

    st.markdown("### Top 5 Destination Counties by Tons Shipped")
    # Add county name to display
    top_dests['county'] = top_dests['dest'].map(
        lambda z: county_meta.loc[county_meta['FIPS'] == z, 'County'].values[0]
        if z in county_meta['FIPS'].values else z
    )
    
    st.table(
        top_dests.rename(columns={
            'dest': 'FIPS',
            'county': 'County',
            'state': 'State',
            'predicted_value_original': 'Tons Shipped',
        })
    )

    # Add button to select number of top links to show
    num_links = st.selectbox(
        "### Number of top links to show ###",
        options=[25, 60, 100, 200],
        index=1 
    )

    # Get top N links by predicted value
    top_n_df = filtered_df.nlargest(num_links, 'predicted_value_original')
    trip_df = convert_sctg_to_trip(top_n_df)



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
    "html": "<b>Origin:</b> {orig_dms} ({object.orig_name})<br/><b>Destination:</b> {dest_dms} ({object.dest_name})",
    "style": {
        "backgroundColor": "steelblue",
        "color": "white"
    }
}

view_state = pdk.ViewState(latitude=39.8283, longitude=-98.5795, zoom=3.5, bearing=0, pitch=45)

with col2:
    st.pydeck_chart(
        pdk.Deck(
            layers=[boundary_layer, layer],
            initial_view_state=view_state,
            tooltip=tooltip
        ),
        use_container_width=True,
        height=1000
    )

