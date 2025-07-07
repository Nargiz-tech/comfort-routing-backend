from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import json
import traceback
import os # Import os to get environment variables for port and DB_CONFIG

# Initialize the Flask application
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing (CORS) to allow requests from your frontend
CORS(app)

# --- Database Connection Function ---
# This function will establish a database connection.
# It's called only when a request needs to interact with the DB,
# ensuring environment variables are fully loaded.
def get_db_connection():
    # Define DB_CONFIG here, reading directly from os.environ
    # This ensures variables are read when the function is called, not on import
    DB_CONFIG_LOCAL = {
        'dbname': os.environ.get('DB_NAME'),
        'user': os.environ.get('DB_USER'),
        'password': os.environ.get('DB_PASSWORD'),
        'host': os.environ.get('DB_HOST'),
        'port': os.environ.get('DB_PORT', '5432') # Default to 5432 if not set
    }

    # Optional: Add a check to ensure all necessary variables are set before connecting
    required_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST']
    for var_name in required_vars:
        if DB_CONFIG_LOCAL.get(var_name.replace('DB_', '').lower()) is None: # Adjust key name for DB_CONFIG_LOCAL
            # This print will appear if a variable is truly missing when get_db_connection is called
            print(f"ERROR: Database environment variable {var_name} is not set.")
            raise ValueError(f"Missing database environment variable: {var_name}")

    try:
        # Attempt to connect using DB_CONFIG_LOCAL
        conn = psycopg2.connect(
            dbname=DB_CONFIG_LOCAL['dbname'],
            user=DB_CONFIG_LOCAL['user'],
            password=DB_CONFIG_LOCAL['password'],
            host=DB_CONFIG_LOCAL['host'],
            port=DB_CONFIG_LOCAL['port']
        )
        return conn
    except Exception as e:
        # Log the specific database connection error for debugging
        print(f"ERROR: Failed to connect to the database. Details: {e}")
        # Re-raise the exception so the calling route handler can catch it
        raise ConnectionError("Could not establish database connection.") from e

@app.route('/')
def home():
    """
    Home route for the Flask application.
    Returns a simple message to indicate the backend is running.
    """
    return "Comfort-based Routing Backend is running!"

@app.route('/route', methods=['POST'])
def generate_route():
    """
    API endpoint to generate comfort-optimized and shortest walking routes.
    Expects a POST request with start/end coordinates and user preferences.
    """
    # Parse incoming JSON data from the request body
    data = request.json

    start_coords = data['start']  # {'lat': ..., 'lon': ...}
    end_coords = data['end']

    # Dictionary to store normalized weights for comfort indicators.
    # Values from frontend (0, 5, 10) are normalized to (0.0, 0.5, 1.0)
    # to be used in the routing cost function.
    weights = {
        'sidewalks': data['sidewalks'] / 10,
        'surface': data['surface'] / 10,
        'speed': data.get('speed', 5) / 10,
        'greenery': data['greenery'] / 10,
        'buildings': data.get('buildings', 5) / 10,
        'crossings': data.get('crossings', 5) / 10,
        'facilities': data.get('facilities', 5) / 10,
        'lanes': data.get('lanes', 5) / 10,
        'water': data.get('water', 5) / 10,
        'benches': data.get('benches', 5) / 10,
        'light': data.get('lights', 5) / 10,    # 'light' corresponds to 'light' column in DB
        'visuals': data.get('attractiveness', 5) / 10, # 'visuals' corresponds to 'visuals' column in DB
        'gradient': data.get('steepness', 5) / 10 # 'gradient' corresponds to 'gradient_norm' in DB
    }

    # Determine the alpha value based on the 'comfort-distance balance' preference.
    # This 'alpha' scales the influence of comfort factors on the route cost.
    # 1: Prioritize Shortness (low alpha), 2: Balanced (medium alpha), 3: Prioritize Comfort (high alpha)
    length_level = data.get('length', 2)
    alpha = {1: 0.5, 2: 5.0, 3: 10.0}.get(length_level, 5.0)

    conn = None
    cursor = None
    try:
        # Establish a connection to the PostgreSQL database using the new function
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT current_user;")
        # This print will now appear after successful connection, not on startup
        print("👤 Current DB User:", cursor.fetchone())

        # Find the nearest graph node (vertex) in the 'munich_roads_vertices_pgr' table
        # for the start coordinates. This is the starting point for routing.
        cursor.execute("""
            SELECT id FROM munich_roads_vertices_pgr
            ORDER BY the_geom <-> ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), ST_SRID(the_geom))
            LIMIT 1
        """, (start_coords['lon'], start_coords['lat']))
        source_id = cursor.fetchone()[0]
        print(f"Source Node ID: {source_id}")

        # Find the nearest graph node (vertex) for the end coordinates.
        # This is the destination point for routing.
        cursor.execute("""
            SELECT id FROM munich_roads_vertices_pgr
            ORDER BY the_geom <-> ST_Transform(ST_SetSRID(ST_Point(%s, %s), 4326), ST_SRID(the_geom))
            LIMIT 1
        """, (end_coords['lon'], end_coords['lat']))
        target_id = cursor.fetchone()[0]
        print(f"Target Node ID: {target_id}")

        # SQL query to calculate both the comfort-optimized route and the shortest route.
        # It uses pgr_dijkstra for routing and selects all relevant road segment properties
        # to be included in the GeoJSON output for frontend visualization.
        sql = f"""
WITH
comfort_route AS (
  SELECT edge FROM pgr_dijkstra(
    '
    SELECT
      gid::BIGINT AS id,
      source,
      target,
      -- Calculate the custom cost for comfort routing:
      -- length * (1 + alpha * sum_of_weighted_uncomfort_factors)
      -- (1 - COALESCE(metric_norm, 0)) converts a normalized comfort score (0-1)
      -- into an uncomfort score (1-0), so higher weight means avoiding less comfortable segments.
      length * (1 + {alpha} * (
                  {weights['gradient']} * (1 - COALESCE(gradient_norm, 0)) +
                  {weights['sidewalks']} * (1 - COALESCE(pedestrian_infrastructure_norm, 0)) +
                  {weights['surface']} * (1 - COALESCE(pavement_norm, 0)) +
                  {weights['speed']} * (1 - COALESCE(max_speed_norm, 0)) +
                  {weights['greenery']} * (1 - COALESCE(greenness_norm, 0)) +
                  {weights['buildings']} * (1 - COALESCE(buildings_norm, 0)) +
                  {weights['crossings']} * (1 - COALESCE(crossings_norm, 0)) +
                  {weights['facilities']} * (1 - COALESCE(facilities_norm, 0)) +
                  {weights['lanes']} * (1 - COALESCE(number_lanes_norm, 0)) +
                  {weights['benches']} * (1 - COALESCE(benches, 0)) +
                  {weights['light']} * (1 - COALESCE(light, 0)) +
                  {weights['visuals']} * (1 - COALESCE(visuals, 0)) +
                  {weights['water']} * (1 - COALESCE(water_norm, 0))
                ))
      AS cost
    FROM munich_roads
    ',
    {source_id}, {target_id}, directed := false
  )
),
shortest_route AS (
  SELECT edge FROM pgr_dijkstra(
    '
    SELECT gid::BIGINT AS id, source, target, length AS cost
    FROM munich_roads
    ',
    {source_id}, {target_id}, directed := false
  )
)

-- Select GeoJSON geometry and all relevant properties for comfort route segments
SELECT
    ST_AsGeoJSON(ST_Transform(r.geom, 4326)) AS geojson_geom,
    'comfort' AS route_type_alias, -- Alias for route type, used in Python
    r.gid,
    r.pedestrian_infrastructure_norm,
    r.pavement_norm,
    r.max_speed_norm,
    r.greenness_norm,
    r.buildings_norm,
    r.crossings_norm,
    r.facilities_norm,
    r.number_lanes_norm,
    r.water_norm,
    r.gradient_norm,
    r.benches,
    r.light,
    r.visuals,
    r.length AS segment_length_meters -- Original segment length
FROM munich_roads AS r
JOIN comfort_route cr ON r.gid = cr.edge

UNION ALL

-- Select GeoJSON geometry and all relevant properties for shortest route segments
SELECT
    ST_AsGeoJSON(ST_Transform(r.geom, 4326)) AS geojson_geom,
    'shortest' AS route_type_alias, -- Alias for route type, used in Python
    r.gid,
    r.pedestrian_infrastructure_norm,
    r.pavement_norm,
    r.max_speed_norm,
    r.greenness_norm,
    r.buildings_norm,
    r.crossings_norm,
    r.facilities_norm,
    r.number_lanes_norm,
    r.water_norm,
    r.gradient_norm,
    r.benches,
    r.light,
    r.visuals,
    r.length AS segment_length_meters
FROM munich_roads AS r
JOIN shortest_route sr ON r.gid = sr.edge;
"""

        # Execute the SQL query to get route geometries and properties
        cursor.execute(sql)
        rows = cursor.fetchall()

        comfort_features = []
        shortest_features = []

        # Define the order of columns returned by the SQL query after geojson_geom (row[0])
        # and route_type_alias (row[1]). These keys will be used to create the properties dictionary.
        feature_property_keys = [
            'gid',
            'pedestrian_infrastructure_norm',
            'pavement_norm',
            'max_speed_norm',
            'greenness_norm',
            'buildings_norm',
            'crossings_norm',
            'facilities_norm',
            'number_lanes_norm',
            'water_norm',
            'gradient_norm',
            'benches',
            'light',
            'visuals',
            'segment_length_meters'
        ]

        # Process each row from the SQL query into a GeoJSON Feature object
        for row in rows:
            geojson_geom_str = row[0] # The GeoJSON geometry string
            current_route_type = row[1] # The route type ('comfort' or 'shortest')
            property_values = row[2:]    # All other values are properties for the segment

            # Create a dictionary of properties using the defined keys and fetched values
            properties = dict(zip(feature_property_keys, property_values))

            # IMPORTANT FIX: Add the route_type to the properties dictionary.
            # This allows the frontend to distinguish between comfort and shortest routes
            # for default styling and visualization.
            properties['route_type'] = current_route_type

            # Construct the final GeoJSON Feature object
            feature = {
                "type": "Feature",
                "geometry": json.loads(geojson_geom_str), # Parse the geometry string to a JSON object
                "properties": properties # Assign the constructed properties dictionary
            }

            # Append the feature to the correct route list
            if current_route_type == 'comfort':
                comfort_features.append(feature)
            else: # current_route_type == 'shortest'
                shortest_features.append(feature)

        print(f"Comfort segments: {len(comfort_features)}, Shortest segments: {len(shortest_features)}")

        # SQL query to calculate aggregated metrics for both comfort and shortest routes.
        # This provides overall statistics for display in the right panel.
        metric_sql = f'''
            WITH
            comfort_route AS (
              SELECT edge FROM pgr_dijkstra(
                '
                SELECT gid::BIGINT AS id, source, target,
                length * (1 + {alpha} * (
                  {weights['gradient']} * (1 - COALESCE(gradient_norm, 0)) +
                  {weights['sidewalks']} * (1 - COALESCE(pedestrian_infrastructure_norm, 0)) +
                  {weights['surface']} * (1 - COALESCE(pavement_norm, 0)) +
                  {weights['speed']} * (1 - COALESCE(max_speed_norm, 0)) +
                  {weights['greenery']} * (1 - COALESCE(greenness_norm, 0)) +
                  {weights['buildings']} * (1 - COALESCE(buildings_norm, 0)) +
                  {weights['crossings']} * (1 - COALESCE(crossings_norm, 0)) +
                  {weights['facilities']} * (1 - COALESCE(facilities_norm, 0)) +
                  {weights['lanes']} * (1 - COALESCE(number_lanes_norm, 0)) +
                  {weights['benches']} * (1 - COALESCE(benches, 0)) +
                  {weights['light']} * (1 - COALESCE(light, 0)) +
                  {weights['visuals']} * (1 - COALESCE(visuals, 0)) +
                  {weights['water']} * (1 - COALESCE(water_norm, 0))
                ))
                 AS cost
                FROM munich_roads
                ',
                {source_id}, {target_id}, directed := false
              )
            ),
            shortest_route AS (
              SELECT edge FROM pgr_dijkstra(
                '
                SELECT gid::BIGINT AS id, source, target, length AS cost
                FROM munich_roads
                ',
                {source_id}, {target_id}, directed := false
              )
            ),
            comfort_data AS (
              SELECT * FROM munich_roads
              WHERE gid IN (SELECT edge FROM comfort_route)
            ),
            shortest_data AS (
              SELECT * FROM munich_roads
              WHERE gid IN (SELECT edge FROM shortest_route)
            )
        
            -- Select aggregated metrics for the comfort route
            SELECT 'comfort' AS type,
                   SUM(length) AS total_length,
                   AVG(pedestrian_infrastructure_norm) AS pedestrian_infrastructure_norm,
                   AVG(pavement_norm) AS pavement_norm,
                   AVG(max_speed_norm) AS max_speed_norm,
                   AVG(greenness_norm) AS greenness_norm,
                   AVG(buildings_norm) AS buildings_norm,
                   AVG(crossings_norm) AS crossings_norm,
                   AVG(facilities_norm) AS facilities_norm,
                   AVG(number_lanes_norm) AS number_lanes_norm,
                   AVG(water_norm) AS water_norm,
                   AVG(benches) AS benches,
                   AVG(light) AS light,
                   AVG(visuals) AS visuals,
                   AVG(gradient_norm) AS gradient_norm
            FROM comfort_data
            
            UNION ALL
            
            -- Select aggregated metrics for the shortest route
            SELECT 'shortest' AS type,
                   SUM(length) AS total_length,
                   AVG(pedestrian_infrastructure_norm) AS pedestrian_infrastructure_norm,
                   AVG(pavement_norm) AS pavement_norm,
                   AVG(max_speed_norm) AS max_speed_norm,
                   AVG(greenness_norm) AS greenness_norm,
                   AVG(buildings_norm) AS buildings_norm,
                   AVG(crossings_norm) AS crossings_norm,
                   AVG(facilities_norm) AS facilities_norm,
                   AVG(number_lanes_norm) AS number_lanes_norm,
                   AVG(water_norm) AS water_norm,
                   AVG(benches) AS benches,
                   AVG(light) AS light,
                   AVG(visuals) AS visuals,
                   AVG(gradient_norm) AS gradient_norm
            FROM shortest_data;
        '''
        print("Executing metrics SQL query...")
        cursor.execute(metric_sql)

        # Define the keys for the aggregated metrics to map fetched rows to a dictionary
        metric_keys = [
            "type", "total_length", "pedestrian_infrastructure_norm", "pavement_norm",
            "max_speed_norm", "greenness_norm", "buildings_norm",
            "crossings_norm", "facilities_norm", "number_lanes_norm",
            "water_norm", "benches", "light", "visuals", "gradient_norm"
        ]
        metrics_list = [dict(zip(metric_keys, row)) for row in cursor.fetchall()]
        # Convert the list of metric dictionaries into a dictionary keyed by route type
        metrics = {m['type']: m for m in metrics_list}
        print("Metrics fetched:", metrics)

        # Return the GeoJSON data for both routes and their aggregated metrics
        return jsonify({
            "comfort": {"type": "FeatureCollection", "features": comfort_features},
            "shortest": {"type": "FeatureCollection", "features": shortest_features},
            "metrics": metrics
        })

    except Exception as e:
        # Catch any exceptions during the process, print traceback, and return an error response
        print("=== ERROR TRACEBACK ===")
        traceback.print_exc() # Print full traceback for debugging
        return jsonify({"error": str(e)}), 500

    finally:
        # Ensure database cursor and connection are closed in all cases
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Run the Flask application in debug mode if executed directly
if __name__ == '__main__':
    # Use 0.0.0.0 for host to make it accessible from outside the container
    # Use PORT environment variable provided by Render, default to 5000 for local dev
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
