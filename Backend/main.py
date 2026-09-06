from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
import os
import shutil

from ocr import run_ocr
from extractor import extract_declarations
from compliance import run_compliance_checks
from comparator import compare_declarations

app = FastAPI(title="LabelLens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.get("/")
def home():
    return {"message": "LabelLens API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/upload")
async def upload_images(
    files: Annotated[list[UploadFile], File()]
):
    results = []

    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            continue

        # Keep the upload filename but avoid allowing a path to escape uploads/.
        safe_filename = os.path.basename(file.filename or "uploaded_image")
        file_path = os.path.join(UPLOAD_FOLDER, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            ocr_result = run_ocr(file_path)

            text = ocr_result["text"]
            lines = ocr_result["lines"]

            declarations = extract_declarations(text, lines)
            compliance = run_compliance_checks(declarations)

            results.append({
                "filename": safe_filename,
                "content_type": file.content_type,

                "extracted_text": text,

                "ocr_confidence": ocr_result["confidence"],
                "ocr_psm": ocr_result["psm"],
                "ocr_passes": ocr_result["passes"],

                "words": ocr_result["words"],
                "lines": ocr_result["lines"],

                "declarations": declarations,
                "compliance": compliance,
            })

        except Exception as e:
            results.append({
                "filename": safe_filename,
                "error": str(e)
            })
    comparisons = compare_declarations(results)

    return {
        "message": "Images processed successfully",
        "results": results,
        "comparisons": comparisons,
    }


# Fix Swagger's file-upload display

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = FastAPI.openapi(app)

    for component in schema.get("components", {}).get("schemas", {}).values():
        for prop in component.get("properties", {}).values():
            items = prop.get("items", {})

            if items.get("contentMediaType") == "application/octet-stream":
                items.pop("contentMediaType", None)
                items["format"] = "binary"

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
