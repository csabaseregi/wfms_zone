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

# Load GeoJSON files
@st.cache_data
def load_zone_data():
    try:
        with open("technical_zones.geojson", "r", encoding="utf-8") as f:
            zones_data = json.load(f)
        return zones_data
    except FileNotFoundError:
        st.error("❌ technical_zones.geojson file not found!")
        return None

# Zone detection function
def find_zone_for_point(lat, lng, zones_data):
    '''Find which zone contains the point, or find nearest zone'''
    point = Point(lng, lat)  # Shapely uses (lng, lat)
    
    # Step 1: Check if point is inside any zone
    for feature in zones_data["features"]:
        polygon = shape(feature["geometry"])
        
        if polygon.contains(point):
            return {
                "zone_id": feature["properties"].get("zone_id"),
                "zone_name": feature["properties"].get("zone_name"),
                "basis_id": feature["properties"].get("basis_id"),
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
    
    # Convert distance to kilometers (approximate for Hungary)
    distance_km = min_distance * 85
    
    return {
        "zone_id": nearest_zone["properties"].get("zone_id"),
        "zone_name": nearest_zone["properties"].get("zone_name"),
        "basis_id": nearest_zone["properties"].get("basis_id"),
        "method": "nearest",
        "confidence": "low",
        "distance_km": round(distance_km, 2)
    }

# Mock addresses for reliable demos
MOCK_ADDRESSES = {
    "Debrecen, Piac utca 1": {"lat": 47.5316, "lng": 21.6273},
    "Debrecen, Bem tér 1": {"lat": 47.5287, "lng": 21.6389},
    "Debrecen, Kossuth utca 5": {"lat": 47.5301, "lng": 21.6250},
    "Debrecen, Hatvan utca 10": {"lat": 47.525, "lng": 21.620},
    "Beled, Füzes utca 12": {"lat": 47.591, "lng": 17.123},
    "Győr, Taligás utca 22": {"lat": 47.688, "lng": 17.635},
}

# Geocoding function
def geocode_address(address):
    '''Convert address to coordinates using mock data or Nominatim'''
    # Try mock database first
    if address in MOCK_ADDRESSES:
        coords = MOCK_ADDRESSES[address]
        return {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "formatted_address": address + ", Hungary (Demo)",
            "success": True,
            "method": "mock"
        }
    
    # Try real geocoding
    try:
        geolocator = Nominatim(user_agent="hungary_zone_lookup_poc")
        
        # Try full address
        location = geolocator.geocode(f"{address}, Hungary", timeout=10)
        
        if location:
            return {
                "lat": location.latitude,
                "lng": location.longitude,
                "formatted_address": location.address,
                "success": True,
                "method": "exact"
            }
        
        # Fallback: try city only
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
        
        return {
            "success": False,
            "error": "Address not found"
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Geocoding error: {str(e)}"
        }

# Initialize session state
if "submissions" not in st.session_state:
    st.session_state.submissions = []

# Main UI
st.title("🗺️ Hungary Zone Lookup System")
st.markdown("### Proof of Concept - Automatic Zone Detection")

# Load zone data
zones_data = load_zone_data()

if zones_data is None:
    st.stop()

# Create layout
col1, col2 = st.columns([2, 1])

with col1:
    st.header("📝 Submission Form")
    
    with st.form("submission_form", clear_on_submit=True):
        # Name
        name = st.text_input(
            "Name *",
            placeholder="Enter your name",
            help="Required field"
        )
        
        # Address selection
        st.subheader("Address")
        address_mode = st.radio(
            "Choose input method:",
            ["Use demo address", "Enter custom address"],
            horizontal=True
        )
        
        if address_mode == "Use demo address":
            address = st.selectbox(
                "Select demo address:",
                list(MOCK_ADDRESSES.keys())
            )
        else:
            address = st.text_input(
                "Enter address:",
                placeholder="e.g., Budapest, Andrássy út 1",
                help="City, Street name format works best"
            )
        
        # Zone display (read-only, will be filled after detection)
        zone_detected = st.empty()
        
        # Other fields
        product = st.text_input("Product", placeholder="Product name (optional)")
        reason = st.text_area("Reason", placeholder="Reason for submission (optional)")
        submission_date = st.date_input("Date", value=date.today())
        
        # Submit button
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn2:
            submitted = st.form_submit_button(
                "🔍 Find Zone & Submit",
                use_container_width=True,
                type="primary"
            )
    
    # Handle form submission
    if submitted:
        if not name:
            st.error("❌ Please enter your name!")
        elif not address:
            st.error("❌ Please enter an address!")
        else:
            # Geocode address
            with st.spinner("🔍 Geocoding address..."):
                geo_result = geocode_address(address)
            
            if not geo_result["success"]:
                st.error(f"❌ {geo_result.get('error', 'Could not find address')}")
            else:
                # Find zone
                with st.spinner("📍 Detecting zone..."):
                    zone_result = find_zone_for_point(
                        geo_result["lat"],
                        geo_result["lng"],
                        zones_data
                    )
                    time.sleep(0.5)  # Small delay for better UX
                
                # Create submission record
                submission = {
                    "timestamp": pd.Timestamp.now(),
                    "name": name,
                    "address": address,
                    "formatted_address": geo_result["formatted_address"],
                    "latitude": round(geo_result["lat"], 6),
                    "longitude": round(geo_result["lng"], 6),
                    "zone_id": zone_result["zone_id"],
                    "zone_name": zone_result["zone_name"],
                    "basis_id": zone_result["basis_id"],
                    "detection_method": zone_result["method"],
                    "confidence": zone_result["confidence"],
                    "distance_km": zone_result.get("distance_km", 0),
                    "product": product if product else "N/A",
                    "reason": reason if reason else "N/A",
                    "date": str(submission_date)
                }
                
                # Save to session
                st.session_state.submissions.append(submission)
                
                # Display success
                st.success("✅ Submission saved successfully!")
                
                # Show zone detection results
                st.markdown("---")
                st.subheader("📊 Zone Detection Results")
                
                result_col1, result_col2, result_col3 = st.columns(3)
                
                with result_col1:
                    st.metric("Zone ID", zone_result["zone_id"])
                with result_col2:
                    st.metric("Zone Name", zone_result["zone_name"])
                with result_col3:
                    st.metric("Basis ID", zone_result["basis_id"])
                
                if zone_result["method"] == "inside":
                    st.info("✅ Address is INSIDE this zone (High confidence)")
                else:
                    st.warning(
                        f"⚠️ Address is OUTSIDE all zones\n\n"
                        f"Nearest zone: **{zone_result['zone_name']}**\n\n"
                        f"Distance: **{zone_result['distance_km']} km**"
                    )
                
                if "note" in geo_result:
                    st.info(f"ℹ️ {geo_result['note']}")

with col2:
    st.header("📊 Statistics")
    
    if st.session_state.submissions:
        total = len(st.session_state.submissions)
        inside = sum(1 for s in st.session_state.submissions if s["detection_method"] == "inside")
        outside = total - inside
        
        st.metric("Total Submissions", total)
        st.metric("Inside Zones", inside, delta=f"{(inside/total*100):.0f}%")
        st.metric("Outside Zones", outside, delta=f"{(outside/total*100):.0f}%")
        
        # Zone distribution
        if total > 0:
            st.markdown("---")
            st.subheader("Zone Distribution")
            zone_counts = {}
            for s in st.session_state.submissions:
                zone = s["zone_name"]
                zone_counts[zone] = zone_counts.get(zone, 0) + 1
            
            for zone, count in sorted(zone_counts.items(), key=lambda x: x[1], reverse=True):
                st.text(f"{zone}: {count}")
    else:
        st.info("No submissions yet\n\nFill the form to get started!")

# Submissions table
if st.session_state.submissions:
    st.markdown("---")
    st.header("📋 All Submissions")
    
    # Create DataFrame
    df = pd.DataFrame(st.session_state.submissions)
    
    # Display columns
    display_cols = [
        "name", "address", "zone_id", "zone_name", 
        "detection_method", "product", "date"
    ]
    
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True
    )
    
    # Export options
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

# Footer
st.markdown("---")
st.caption("🗺️ Hungary Zone Lookup System | Proof of Concept | Automatic zone detection based on address geocoding")
