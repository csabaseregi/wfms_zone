import streamlit as st
import json
from shapely.geometry import shape, Point
from geopy.geocoders import Nominatim
import pandas as pd
from datetime import date
import time

# Configure page
st.set_page_config(
    page_title="Hungary Zone Lookup",
    page_icon="🗺️",
    layout="wide"
)

# Load mock addresses from JSON file
@st.cache_data
def load_mock_addresses():
    '''Load mock addresses from JSON file'''
    try:
        with open("mock_addresses_simple.json", "r", encoding="utf-8") as f:
            addresses = json.load(f)
            return addresses
    except FileNotFoundError:
        st.warning("⚠️ mock_addresses_simple.json not found, using fallback addresses")
        # Fallback to a few default addresses
        return {
            "Debrecen, Piac utca 1": {"lat": 47.5316, "lng": 21.6273},
            "Győr, Baross út 1": {"lat": 47.686, "lng": 17.635},
        }

# Load ALL GeoJSON files
@st.cache_data
def load_all_data():
    '''Load regions, branches, and technical zones'''
    data = {}
    
    # Load regions
    try:
        with open("regions.geojson", "r", encoding="utf-8") as f:
            data['regions'] = json.load(f)
    except FileNotFoundError:
        st.warning("⚠️ regions.geojson not found")
        data['regions'] = None
    
    # Load branches
    try:
        with open("branches.geojson", "r", encoding="utf-8") as f:
            data['branches'] = json.load(f)
    except FileNotFoundError:
        st.warning("⚠️ branches.geojson not found")
        data['branches'] = None
    
    # Load technical zones
    try:
        with open("technical_zones.geojson", "r", encoding="utf-8") as f:
            data['zones'] = json.load(f)
    except FileNotFoundError:
        st.error("❌ technical_zones.geojson not found!")
        data['zones'] = None
    
    return data

# Helper function: Find which region a point is in
def find_region_for_point(lat, lng, regions_data):
    '''Find which region contains the point'''
    if not regions_data:
        return None
    
    point = Point(lng, lat)
    
    for feature in regions_data["features"]:
        polygon = shape(feature["geometry"])
        if polygon.contains(point):
            return {
                "region_id": feature["properties"].get("region_id"),
                "region_name": feature["properties"].get("region_name")
            }
    return None

# Helper function: Find which branch a point is in
def find_branch_for_point(lat, lng, branches_data):
    '''Find which branch contains the point'''
    if not branches_data:
        return None
    
    point = Point(lng, lat)
    
    for feature in branches_data["features"]:
        polygon = shape(feature["geometry"])
        if polygon.contains(point):
            return {
                "branch_id": feature["properties"].get("branch_id"),
                "branch_name": feature["properties"].get("branch_name"),
                "region_id": feature["properties"].get("region_id")
            }
    return None

# Zone detection function - HANDLES HUNGARIAN FIELD NAMES
def find_zone_for_point(lat, lng, zones_data):
    '''Find which zone contains the point, or find nearest zone'''
    point = Point(lng, lat)
    
    # Step 1: Check if point is inside any zone
    for feature in zones_data["features"]:
        polygon = shape(feature["geometry"])
        
        if polygon.contains(point):
            props = feature["properties"]
            return {
                "zone_id": props.get("bázis_id") or props.get("zone_id"),
                "zone_name": props.get("bázis_név") or props.get("zone_name"),
                "region_name": props.get("Régió"),
                "created_by": props.get("created_by"),
                "status": props.get("status"),
                "method": "inside",
                "confidence": "high"
            }
    
    # Step 2: Find nearest zone (by centroid distance)
    nearest_zone = None
    min_distance = float("inf")
    
    for feature in zones_data["features"]:
        polygon = shape(feature["geometry"])
        centroid = polygon.centroid
        distance = point.distance(centroid)
        
        if distance < min_distance:
            min_distance = distance
            nearest_zone = feature
    
    # Convert distance to kilometers
    distance_km = min_distance * 85
    
    props = nearest_zone["properties"]
    return {
        "zone_id": props.get("bázis_id") or props.get("zone_id"),
        "zone_name": props.get("bázis_név") or props.get("zone_name"),
        "region_name": props.get("Régió"),
        "created_by": props.get("created_by"),
        "status": props.get("status"),
        "method": "nearest",
        "confidence": "low",
        "distance_km": round(distance_km, 2)
    }

# Geocoding function
def geocode_address(address, mock_addresses):
    '''Convert address to coordinates using mock data or real geocoding'''
    # Check mock database first
    if address in mock_addresses:
        coords = mock_addresses[address]
        return {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "formatted_address": address + " (Demo)",
            "success": True,
            "method": "mock"
        }
    
    # Try real geocoding
    try:
        geolocator = Nominatim(user_agent="hungary_zone_lookup_poc")
        location = geolocator.geocode(f"{address}, Hungary", timeout=10)
        
        if location:
            return {
                "lat": location.latitude,
                "lng": location.longitude,
                "formatted_address": location.address,
                "success": True,
                "method": "exact"
            }
        
        # Fallback: city only
        city = address.split(",")[0].strip()
        location = geolocator.geocode(f"{city}, Hungary", timeout=10)
        
        if location:
            return {
                "lat": location.latitude,
                "lng": location.longitude,
                "formatted_address": location.address,
                "success": True,
                "method": "city_only",
                "note": f"Street not found, using {city} city center"
            }
        
        return {"success": False, "error": "Address not found"}
    
    except Exception as e:
        return {"success": False, "error": f"Geocoding error: {str(e)}"}

# Initialize session state
if "submissions" not in st.session_state:
    st.session_state.submissions = []

# Load data
mock_addresses = load_mock_addresses()
all_data = load_all_data()

# Main UI
st.title("🗺️ Hungary Zone Lookup System")
st.markdown(f"### Proof of Concept | {len(mock_addresses)} Demo Addresses Available")

if all_data['zones'] is None:
    st.error("❌ Cannot load technical zones!")
    st.stop()

# Layout
col1, col2 = st.columns([2, 1])

with col1:
    st.header("📝 Submission Form")
    
    with st.form("submission_form", clear_on_submit=True):
        name = st.text_input("Name *", placeholder="Enter your name")
        
        st.subheader("Address")
        
        # Show info about available addresses
        st.info(f"ℹ️ {len(mock_addresses)} demo addresses available covering all zones")
        
        address_mode = st.radio(
            "Choose input method:",
            ["Use demo address", "Enter custom address"],
            horizontal=True
        )
        
        if address_mode == "Use demo address":
            # Create searchable selectbox with all mock addresses
            address = st.selectbox(
                "Select or search demo address:",
                options=sorted(mock_addresses.keys()),
                help="Type to search addresses"
            )
        else:
            address = st.text_input(
                "Enter address:",
                placeholder="e.g., Budapest, Andrássy út 1"
            )
        
        product = st.text_input("Product", placeholder="Product name (optional)")
        reason = st.text_area("Reason", placeholder="Reason for submission (optional)")
        submission_date = st.date_input("Date", value=date.today())
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn2:
            submitted = st.form_submit_button(
                "🔍 Find Zone & Submit",
                use_container_width=True,
                type="primary"
            )
    
    if submitted:
        if not name or not address:
            st.error("❌ Please fill in Name and Address!")
        else:
            with st.spinner("🔍 Processing..."):
                geo_result = geocode_address(address, mock_addresses)
            
            if not geo_result["success"]:
                st.error(f"❌ {geo_result.get('error')}")
            else:
                # Find location hierarchy
                region_result = find_region_for_point(
                    geo_result["lat"], geo_result["lng"], all_data['regions']
                )
                branch_result = find_branch_for_point(
                    geo_result["lat"], geo_result["lng"], all_data['branches']
                )
                
                with st.spinner("📍 Detecting zone..."):
                    zone_result = find_zone_for_point(
                        geo_result["lat"], geo_result["lng"], all_data['zones']
                    )
                
                # Create submission
                submission = {
                    "timestamp": pd.Timestamp.now(),
                    "name": name,
                    "address": address,
                    "formatted_address": geo_result["formatted_address"],
                    "latitude": round(geo_result["lat"], 6),
                    "longitude": round(geo_result["lng"], 6),
                    "region_id": region_result["region_id"] if region_result else "N/A",
                    "region_name": region_result["region_name"] if region_result else (zone_result.get("region_name") or "N/A"),
                    "branch_id": branch_result["branch_id"] if branch_result else "N/A",
                    "branch_name": branch_result["branch_name"] if branch_result else "N/A",
                    "zone_id": zone_result["zone_id"],
                    "zone_name": zone_result["zone_name"],
                    "status": zone_result.get("status", "N/A"),
                    "created_by": zone_result.get("created_by", "N/A"),
                    "detection_method": zone_result["method"],
                    "confidence": zone_result["confidence"],
                    "distance_km": zone_result.get("distance_km", 0),
                    "product": product or "N/A",
                    "reason": reason or "N/A",
                    "date": str(submission_date)
                }
                
                st.session_state.submissions.append(submission)
                st.success("✅ Submission saved successfully!")
                
                # Display results
                st.markdown("---")
                st.subheader("📊 Location Detection Results")
                
                result_col1, result_col2, result_col3 = st.columns(3)
                
                with result_col1:
                    st.markdown("**🌍 Region**")
                    if region_result:
                        st.metric("Region ID", region_result["region_id"])
                        st.metric("Region Name", region_result["region_name"])
                    else:
                        st.metric("Region Name", zone_result.get("region_name", "N/A"))
                
                with result_col2:
                    st.markdown("**🏢 Branch**")
                    if branch_result:
                        st.metric("Branch ID", branch_result["branch_id"])
                        st.metric("Branch Name", branch_result["branch_name"])
                    else:
                        st.info("Not detected")
                
                with result_col3:
                    st.markdown("**📍 Technical Zone (Base)**")
                    st.metric("Zone ID", zone_result["zone_id"])
                    st.metric("Zone Name", zone_result["zone_name"])
                    st.caption(f"Status: {zone_result.get('status', 'N/A')}")
                
                st.markdown("---")
                if zone_result["method"] == "inside":
                    st.info("✅ Address is INSIDE this zone (High confidence)")
                else:
                    st.warning(f"⚠️ Address is OUTSIDE all zones\n\nNearest zone: **{zone_result['zone_name']}**\n\nDistance: **{zone_result['distance_km']} km**")
                
                if "note" in geo_result:
                    st.info(f"ℹ️ {geo_result['note']}")

with col2:
    st.header("📊 Statistics")
    
    if st.session_state.submissions:
        total = len(st.session_state.submissions)
        inside = sum(1 for s in st.session_state.submissions if s["detection_method"] == "inside")
        
        st.metric("Total Submissions", total)
        st.metric("Inside Zones", inside, delta=f"{(inside/total*100):.0f}%")
        st.metric("Outside Zones", total - inside)
        
        if total > 0:
            st.markdown("---")
            st.subheader("Region Distribution")
            region_counts = {}
            for s in st.session_state.submissions:
                region = s.get("region_name", "Unknown")
                region_counts[region] = region_counts.get(region, 0) + 1
            
            for region, count in sorted(region_counts.items(), key=lambda x: x[1], reverse=True):
                st.text(f"{region}: {count}")
    else:
        st.info("No submissions yet\n\nFill the form to get started!")

# Submissions table
if st.session_state.submissions:
    st.markdown("---")
    st.header("📋 All Submissions")
    
    df = pd.DataFrame(st.session_state.submissions)
    
    display_cols = ["name", "address", "region_name", "branch_name", "zone_name", "status", "detection_method", "date"]
    
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
    
    col_export1, col_export2 = st.columns(2)
    
    with col_export1:
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download as CSV",
            data=csv,
            file_name=f"zone_submissions_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_export2:
        if st.button("🗑️ Clear All Submissions", use_container_width=True):
            st.session_state.submissions = []
            st.rerun()

st.markdown("---")
st.caption("🗺️ Hungary Zone Lookup System | PoC | Region → Branch → Technical Zone (Base)")
