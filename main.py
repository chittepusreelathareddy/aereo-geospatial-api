import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from services import process_geospatial_file, FILE_STORE

app = FastAPI(
    title="Aereo Geospatial File Measurement API",
    description="Backend service for processing Shapefiles and KML files, handling CRS transformations, and calculating spatial measurements.",
    version="1.0.0"
)

@app.post("/api/files/", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name

    try:
        file_id = process_geospatial_file(temp_file_path, file.filename)
        file_info = FILE_STORE[file_id]
        return {
            "id": file_info["id"],
            "filename": file_info["filename"],
            "feature_count": file_info["feature_count"],
            "crs": file_info["crs"],
            "status": file_info["status"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/api/files/{file_id}/")
async def get_file_info(file_id: str):
    if file_id not in FILE_STORE:
        raise HTTPException(status_code=404, detail="File ID not found.")
    
    file_info = FILE_STORE[file_id]
    return {
        "id": file_info["id"],
        "filename": file_info["filename"],
        "feature_count": file_info["feature_count"],
        "crs": file_info["crs"],
        "status": file_info["status"]
    }

@app.get("/api/files/{file_id}/measurements/")
async def get_file_measurements(file_id: str):
    if file_id not in FILE_STORE:
        raise HTTPException(status_code=404, detail="File ID not found.")
    
    file_info = FILE_STORE[file_id]
    return {
        "id": file_info["id"],
        "filename": file_info["filename"],
        "total_features": file_info["feature_count"],
        "features": file_info["features"]
    }
