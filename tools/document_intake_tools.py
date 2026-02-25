from __future__ import annotations

import io
import re
from typing import Dict, List


class DocumentIntakeTools:
    """Lightweight upload/OCR intake helpers with optional dependencies."""

    def analyze_upload(self, filename: str, mime_type: str, content: bytes) -> Dict[str, object]:
        safe_name = (filename or "upload").strip() or "upload"
        mime = (mime_type or "application/octet-stream").lower()
        text = ""
        warnings: List[str] = []
        extraction_method = "heuristic"

        if mime.startswith("text/"):
            try:
                text = content.decode("utf-8", errors="ignore")
                extraction_method = "text"
            except Exception:
                warnings.append("text_decode_failed")
        elif "pdf" in mime:
            parsed = self._try_pdf_extract(content)
            text = parsed.get("text", "")
            extraction_method = parsed.get("method", extraction_method)
            warnings.extend(parsed.get("warnings", []))
        elif mime.startswith("image/"):
            parsed = self._try_image_ocr(content)
            text = parsed.get("text", "")
            extraction_method = parsed.get("method", extraction_method)
            warnings.extend(parsed.get("warnings", []))

        if not text:
            text = safe_name

        extracted = self._extract_entities(text + " " + safe_name)
        suggested_message = self._suggest_message(extracted, text)
        return {
            "ok": True,
            "filename": safe_name,
            "mime_type": mime,
            "extraction_method": extraction_method,
            "text_preview": (text or "").strip()[:500],
            "entities": extracted,
            "suggested_message": suggested_message,
            "warnings": warnings,
        }

    def _try_pdf_extract(self, content: bytes) -> Dict[str, object]:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            return {"text": "", "method": "pdf_heuristic", "warnings": ["pypdf_not_available"]}
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:5]).strip()
            return {"text": text, "method": "pypdf", "warnings": []}
        except Exception:
            return {"text": "", "method": "pdf_heuristic", "warnings": ["pdf_extract_failed"]}

    def _try_image_ocr(self, content: bytes) -> Dict[str, object]:
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
        except Exception:
            return {"text": "", "method": "image_heuristic", "warnings": ["ocr_dependencies_not_available"]}
        try:
            img = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(img).strip()
            return {"text": text, "method": "pytesseract", "warnings": []}
        except Exception:
            return {"text": "", "method": "image_heuristic", "warnings": ["ocr_failed"]}

    def _extract_entities(self, text: str) -> Dict[str, object]:
        upper = text.upper()
        entities: Dict[str, object] = {}

        flight = re.search(r"\b(F8\d{3,4})\b", upper)
        if flight:
            entities["flight_number"] = flight.group(1)

        pnr_candidates = re.findall(r"\b[A-Z0-9]{6}\b", upper)
        for cand in pnr_candidates:
            if any(ch.isdigit() for ch in cand) and not re.fullmatch(r"F8\d{4,5}", cand):
                entities["booking_reference"] = cand
                break

        claim = re.search(r"\b([A-Z]{2}\d{7,10})\b", upper)
        if claim:
            entities["baggage_claim_number"] = claim.group(1)

        amount = re.search(r"(?:(?:CAD|USD)\s*|\$)\s*(\d{1,4}(?:\.\d{2})?)\b", upper)
        if amount:
            try:
                entities["charge_amount"] = float(amount.group(1))
            except ValueError:
                pass

        return entities

    def _suggest_message(self, entities: Dict[str, object], text: str) -> str:
        lower = (text or "").lower()
        if entities.get("baggage_claim_number") or "baggage" in lower or "claim tag" in lower:
            claim = entities.get("baggage_claim_number", "the claim number from this upload")
            pnr = entities.get("booking_reference")
            if pnr:
                return f"My bag is missing. Claim number {claim}. Booking reference {pnr}."
            return f"My bag is missing. Claim number {claim}."
        if "refund" in lower or "charge" in lower or "receipt" in lower:
            pnr = entities.get("booking_reference")
            if pnr:
                return f"I need help with a refund or charge issue for booking {pnr}."
            return "I need help with a refund or charge issue."
        if entities.get("flight_number"):
            return f"What is the status of flight {entities['flight_number']}?"
        if entities.get("booking_reference"):
            return f"Please check booking reference {entities['booking_reference']}."
        return "I uploaded a document. Please help me with the details from it."
