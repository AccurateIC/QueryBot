import os
import io
import fitz  
from pdf2image import convert_from_path
import pytesseract
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader


def is_scanned_pdf(pdf_path):
    """
    Returns True if no extractable text is found in the PDF (i.e., scanned).
    """
    doc = fitz.open(pdf_path)
    for page in doc:
        if page.get_text().strip():  
            return True


def scanned_to_digital_pdf(input_pdf, output_pdf):
    """
    Converts a scanned PDF (image-only) into a searchable digital PDF using OCR.
    """
    print("Converting scanned PDF to digital PDF with OCR...")

    # Convert each page to an image
    images = convert_from_path(input_pdf)
    c = canvas.Canvas(output_pdf, pagesize=letter)

    for idx, image in enumerate(images):
        # OCR to extract text
        text = pytesseract.image_to_string(image)

        # Convert image to binary stream
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        img_reader = ImageReader(img_byte_arr)

        # Draw the image (acts as background)
        c.drawImage(img_reader, 0, 0, width=letter[0], height=letter[1])

        # Optional: draw invisible OCR text layer (advanced: for searchable PDFs)
        # For simplicity, just print OCR text on top in a visible layer
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0, 0, 0)
        text_lines = text.split('\n')
        y = 750
        for line in text_lines:
            if y < 20:  # move to new page if too low
                c.showPage()
                c.setFont("Helvetica", 8)
                y = 750
            c.drawString(40, y, line.strip())
            y -= 12

        c.showPage()

    c.save()
    print(f"Saved searchable PDF to: {output_pdf}")


def main(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return
    output_pdf = os.path.splitext(pdf_path)[0] + "_digital.pdf"
    scanned_to_digital_pdf(pdf_path, output_pdf)
    # else:
    #     print("PDF is already digital (contains selectable text). No conversion needed.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python convert_scanned_pdf.py <input.pdf>")
    else:
        main(sys.argv[1])
