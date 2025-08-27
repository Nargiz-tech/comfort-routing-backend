Comfort-Based Routing: GIS Web Tool

This repository contains the implementation of a comfort-based pedestrian routing system developed as part of my Master’s thesis, “Beyond Distance: Integrating Walkability Indicators for User-Centered Pedestrian Navigation.” 
The system helps users find not only the shortest path, but also the most comfortable walking routes based on their personal preferences.

🔑 Key Components

Frontend (Interface)

Built with HTML (structure), Tailwind CSS (design), and JavaScript (logic).
Uses Leaflet.js to display an interactive map where users can set start/end points and visualize routing results.

Backend (Server)

Implemented in Python with the Flask framework.
Exposes an API that receives user requests (start/end points + preferences) and returns calculated routes.
Database & Algorithms
Core functionality built on PostgreSQL with the PostGIS extension for geospatial data.
Routing is handled by pgRouting, running a modified Dijkstra algorithm.

Instead of only computing shortest paths, the algorithm incorporates user-defined weights into a multi-criteria cost function, producing both:

a shortest-distance route
a comfort-optimized route

⚙️ How It Works

The user selects start and end points on the map and adjusts comfort preferences.

The frontend sends the request to the Flask server.
The server queries the PostgreSQL database, where pgRouting computes two routes:

shortest path,
comfort-optimized path (based on user weights).
The results are returned to the frontend and displayed on the interactive Leaflet.js map for comparison.

📂 Data Sources

The system relies on openly available geospatial datasets. Due to their size, processed datasets are not included in this repository. They can be reproduced from the following sources:

NetAScore – street-level indicators (traffic exposure, greenery, amenities, etc.).
Documentation: (https://github.com/plus-mobilitylab/netascore) 

OpenStreetMap (OSM) – pedestrian network and amenities.
Access via Overpass API or Geofabrik

Digital Elevation Models (DEM) – slope/terrain data.
Example: (https://geodaten.bayern.de/opengeodata/OpenDataDetail.html?pn=dgm1)

Reproducing the Data

Extract NetAScore indicators for your study area.
Download pedestrian networks from OSM.
Add DEM for slope analysis.
Normalize and preprocess layers.
