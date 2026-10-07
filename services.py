import os
import shutil
import tempfile
import uuid
import zipfile
from typing import Dict, Any, List
import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

FILE_STORE: Dict[str, Dict[str, Any]] = {}

def process_geospatial_file(file_path: str, original_filename: str) -> str:
    file_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp()
    
    try:
        name = original_filename.lower()
        if name.endswith('.zip'):
            with zipfile.ZipFile(file_path) as zf:
                zf.extractall(temp_dir)
            shp_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith('.shp'):
                        shp_file = os.path.join(root, file)
                        break
                if shp_file:
                    break
            if not shp_file:
                raise ValueError("No .shp file found inside the uploaded ZIP archive.")
            gdf = gpd.read_file(shp_file)
        elif name.endswith('.kml') or name.endswith('.kmz'):
            gdf = gpd.read_file(file_path)
        else:
            raise ValueError("Unsupported file format. Please upload a .zip (Shapefile) or .kml file.")

        original_crs = str(gdf.crs) if gdf.crs else "EPSG:4326"
        
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
            original_crs = "EPSG:4326"

        projected_gdf = gdf.copy()
        if gdf.crs.is_geographic:
            try:
                utm_crs = gdf.estimate_utm_crs()
                projected_gdf = gdf.to_crs(utm_crs)
            except Exception:
                projected_gdf = gdf.to_crs("EPSG:3395")

        features_data = []
        for idx, (orig_row, proj_row) in enumerate(zip(gdf.itertuples(), projected_gdf.itertuples())):
            geom: BaseGeometry = orig_row.geometry
            proj_geom: BaseGeometry = proj_row.geometry
            
            if geom is None:
                continue

            geom_type = geom.geom_type
            measurement = None
            unit = None
            status = "SUPPORTED"

            if geom_type == "Polygon" or geom_type == "MultiPolygon":
                measurement = proj_geom.area
                unit = "square_meters"
            elif geom_type == "LineString" or geom_type == "MultiLineString":
                measurement = proj_geom.length
                unit = "meters"
            elif geom_type == "Point" or geom_type == "MultiPoint":
                measurement = 0.0
                unit = "none"
            else:
                status = "UNSUPPORTED_GEOMETRY"

            properties = {k: v for k, v in orig_row._asdict().items() if k not in ['Index', 'geometry']}
            properties = {k: (v if not isinstance(v, (bytes,)) else v.decode('utf-8', errors='ignore')) for k, v in properties.items()}
            properties = {k: (None if not isinstance(v, (list, dict, tuple)) and pd.isna(v) else (str(v) if isinstance(v, pd.Timestamp) else v)) for k, v in properties.items()}

            features_data.append({
                "feature_id": idx,
                "geometry_type": geom_type,
                "geometry": geom.wkt,
                "measurement": measurement,
                "unit": unit,
                "status": status,
                "properties": properties
            })

        FILE_STORE[file_id] = {
            "id": file_id,
            "filename": original_filename,
            "feature_count": len(features_data),
            "crs": original_crs,
            "status": "COMPLETED",
            "features": features_data
        }

        return file_id

    except Exception as e:
        FILE_STORE[file_id] = {
            "id": file_id,
            "filename": original_filename,
            "feature_count": 0,
            "crs": "UNKNOWN",
            "status": f"FAILED: {str(e)}",
            "features": []
        }
        raise e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
