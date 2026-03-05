from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import os
import uuid

app = FastAPI()

EXPORT_FOLDER = "exports"
os.makedirs(EXPORT_FOLDER, exist_ok=True)


class ScrapeRequest(BaseModel):
    url: str
    query: str = ""


def run_scraper(url, query, output_file):
    """
    Run the scraping pipeline here
    Replace this with your real scraping code
    """

    # Example command
    # python scraper.py --url URL --output FILE

    subprocess.run([
        "python",
        "scraper.py",
        "--url", url,
        "--query", query,
        "--output", output_file
    ])


@app.post("/extract")
async def extract_data(request: ScrapeRequest, background_tasks: BackgroundTasks):

    job_id = str(uuid.uuid4())
    output_file = f"{EXPORT_FOLDER}/{job_id}.xlsx"

    background_tasks.add_task(
        run_scraper,
        request.url,
        request.query,
        output_file
    )

    return {
        "status": "processing",
        "job_id": job_id
    }


@app.get("/download/{job_id}")
def download_file(job_id: str):

    file_path = f"{EXPORT_FOLDER}/{job_id}.xlsx"

    if not os.path.exists(file_path):
        return {"error": "File not ready"}

    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="dataset.xlsx"
    )
