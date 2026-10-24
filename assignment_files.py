"""Extract assignment text from uploaded documents and ask OpenAI to structure it."""
import base64
import json
import os
from io import BytesIO
from openai import OpenAI


def _extract_text(uploaded_file):
    name = uploaded_file.name
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    data = uploaded_file.getvalue()
    if suffix == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip(), None
    if suffix == "docx":
        from docx import Document
        doc = Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip(), None
    if suffix in ("txt", "md", "csv"):
        return data.decode("utf-8", errors="replace").strip(), None
    if suffix in ("png", "jpg", "jpeg", "webp"):
        mime = "image/png" if suffix == "png" else "image/webp" if suffix == "webp" else "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        return "", f"data:{mime};base64,{encoded}"
    raise ValueError("Supported formats: PDF, DOCX, TXT, MD, CSV, PNG, JPG, JPEG, and WEBP.")


def extract_assignment_details(uploaded_file):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    text, image_data_url = _extract_text(uploaded_file)
    if not text and not image_data_url:
        raise ValueError("No readable text was found. If this is a scanned PDF, upload page images or a text-based PDF.")
    client = OpenAI()
    instructions = (
        "Extract assignment metadata from the provided university assignment brief. Return only a JSON object with keys: "
        "title (string), course (string or empty), due_date (YYYY-MM-DD or empty), priority (low/medium/high), "
        "estimate_minutes (integer 30-600), instructions (short string). Do not guess a deadline or course. "
        "If the year or date is ambiguous, leave due_date empty and mention the ambiguity in instructions. "
        "Use high priority only if the document explicitly signals high weight/urgency or the deadline is near; otherwise medium."
    )
    content = [{"type": "input_text", "text": instructions}]
    if text:
        content.append({"type": "input_text", "text": f"Filename: {uploaded_file.name}\nDocument text:\n{text[:24000]}"})
    if image_data_url:
        content.append({"type": "input_image", "image_url": image_data_url})
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}},
    )
    try:
        details = json.loads(response.output_text)
    except Exception as exc:
        raise RuntimeError("OpenAI could not structure the assignment details. Please enter them manually.") from exc
    details.setdefault("title", uploaded_file.name)
    details.setdefault("course", "")
    details.setdefault("due_date", "")
    details.setdefault("priority", "medium")
    details.setdefault("estimate_minutes", 60)
    details.setdefault("instructions", "")
    if details.get("priority") not in ("low", "medium", "high"):
        details["priority"] = "medium"
    try:
        details["estimate_minutes"] = max(5, min(600, int(details["estimate_minutes"])))
    except (ValueError, TypeError):
        details["estimate_minutes"] = 60
    return details
