# -*- coding: utf-8 -*-

import logging
import base64
import io
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OCRExtractionService(models.Model):
    """OCR Extraction Service for Document Text Recognition"""

    _name = 'dms.ocr.extraction.service'
    _description = 'OCR Extraction Service'

    name = fields.Char(string='Service Name', required=True)
    active = fields.Boolean(default=True)

    provider = fields.Selection([
        ('tesseract', 'Tesseract OCR (Local)'),
        ('azure', 'Azure Form Recognizer'),
        ('google', 'Google Cloud Vision'),
        ('aws', 'AWS Textract'),
    ], string='OCR Provider', required=True, default='tesseract')

    api_key = fields.Char(string='API Key', groups='base.group_system')
    api_endpoint = fields.Char(string='API Endpoint')

    # OCR Settings
    languages = fields.Char(
        string='Languages',
        default='deu+eng',
        help='Languages for OCR (e.g., deu+eng for German and English)',
    )

    dpi = fields.Integer(
        string='DPI for PDF Conversion',
        default=300,
        help='DPI resolution for converting PDFs to images',
    )

    enhance_image = fields.Boolean(
        string='Enhance Image',
        default=True,
        help='Apply image enhancement before OCR',
    )

    # Statistics
    documents_processed = fields.Integer(
        string='Documents Processed',
        readonly=True,
    )

    last_run = fields.Datetime(string='Last Run', readonly=True)

    def extract_text(self, document):
        """Extract text from document attachment"""
        self.ensure_one()

        if not document.attachment_ids:
            return {'error': 'No attachment found'}

        attachment = document.attachment_ids[0]

        try:
            if attachment.mimetype == 'application/pdf':
                # Convert PDF to images first
                images = self._pdf_to_images(attachment.raw)
                text_parts = []
                for img_data in images:
                    text = self._extract_text_from_image(img_data)
                    if text:
                        text_parts.append(text)
                full_text = '\n\n--- Page Break ---\n\n'.join(text_parts)
            elif attachment.mimetype and attachment.mimetype.startswith('image/'):
                full_text = self._extract_text_from_image(attachment.raw)
            else:
                return {'error': f'Unsupported file type: {attachment.mimetype}'}

            # Update statistics
            self.sudo().write({
                'documents_processed': self.documents_processed + 1,
                'last_run': fields.Datetime.now(),
            })

            return {
                'text': full_text,
                'pages': len(images) if attachment.mimetype == 'application/pdf' else 1,
                'provider': self.provider,
            }

        except Exception as e:
            _logger.exception(f"OCR extraction error: {e}")
            return {'error': str(e)}

    def _pdf_to_images(self, pdf_data):
        """Convert PDF pages to images"""
        images = []

        try:
            # Try pdf2image (requires poppler)
            from pdf2image import convert_from_bytes
            pil_images = convert_from_bytes(pdf_data, dpi=self.dpi)
            for pil_img in pil_images:
                img_buffer = io.BytesIO()
                pil_img.save(img_buffer, format='PNG')
                images.append(img_buffer.getvalue())
        except ImportError:
            _logger.warning("pdf2image not installed, trying PyMuPDF")
            try:
                # Fallback to PyMuPDF (fitz)
                import fitz
                doc = fitz.open(stream=pdf_data, filetype='pdf')
                for page in doc:
                    mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                    pix = page.get_pixmap(matrix=mat)
                    images.append(pix.tobytes('png'))
                doc.close()
            except ImportError:
                _logger.error("Neither pdf2image nor PyMuPDF installed")
                raise UserError(_('PDF processing requires pdf2image or PyMuPDF. '
                                'Please install: pip install pdf2image or pip install PyMuPDF'))

        return images

    def _extract_text_from_image(self, image_data):
        """Extract text from image using configured provider"""
        if self.provider == 'tesseract':
            return self._ocr_tesseract(image_data)
        elif self.provider == 'azure':
            return self._ocr_azure(image_data)
        elif self.provider == 'google':
            return self._ocr_google(image_data)
        elif self.provider == 'aws':
            return self._ocr_aws(image_data)
        else:
            return f'Provider {self.provider} not implemented'

    def _ocr_tesseract(self, image_data):
        """OCR using local Tesseract"""
        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            raise UserError(_('Tesseract OCR requires: pip install pytesseract pillow\n'
                            'Also install Tesseract: brew install tesseract tesseract-lang'))

        # Load image
        img = Image.open(io.BytesIO(image_data))

        # Image enhancement
        if self.enhance_image:
            img = self._enhance_image_pil(img)

        # Perform OCR
        text = pytesseract.image_to_string(
            img,
            lang=self.languages or 'deu+eng',
            config='--psm 1'  # Automatic page segmentation with OSD
        )

        return text

    def _enhance_image_pil(self, img):
        """Apply image enhancements for better OCR"""
        try:
            from PIL import ImageEnhance, ImageFilter
        except ImportError:
            return img

        # Convert to grayscale if not already
        if img.mode != 'L':
            img = img.convert('L')

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        return img

    def _ocr_azure(self, image_data):
        """OCR using Azure Form Recognizer"""
        try:
            from azure.ai.formrecognizer import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError:
            raise UserError(_('Azure OCR requires: pip install azure-ai-formrecognizer'))

        if not self.api_key or not self.api_endpoint:
            raise UserError(_('Azure API key and endpoint are required'))

        client = DocumentAnalysisClient(
            endpoint=self.api_endpoint,
            credential=AzureKeyCredential(self.api_key)
        )

        poller = client.begin_analyze_document(
            'prebuilt-read',
            image_data
        )
        result = poller.result()

        # Extract text from result
        text_parts = []
        for page in result.pages:
            for line in page.lines:
                text_parts.append(line.content)

        return '\n'.join(text_parts)

    def _ocr_google(self, image_data):
        """OCR using Google Cloud Vision"""
        try:
            from google.cloud import vision
        except ImportError:
            raise UserError(_('Google OCR requires: pip install google-cloud-vision'))

        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_data)

        response = client.document_text_detection(image=image)

        if response.error.message:
            raise UserError(f'Google Vision error: {response.error.message}')

        return response.full_text_annotation.text

    def _ocr_aws(self, image_data):
        """OCR using AWS Textract"""
        try:
            import boto3
        except ImportError:
            raise UserError(_('AWS OCR requires: pip install boto3'))

        client = boto3.client('textract')

        response = client.detect_document_text(
            Document={'Bytes': image_data}
        )

        text_parts = []
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                text_parts.append(block['Text'])

        return '\n'.join(text_parts)


class DocumentsDocumentOCR(models.Model):
    """Extend documents.document with OCR capabilities"""

    _inherit = 'documents.document'

    ocr_text = fields.Text(
        string='OCR Text',
        help='Extracted text from OCR processing',
    )

    ocr_processed = fields.Boolean(
        string='OCR Processed',
        default=False,
    )

    ocr_date = fields.Datetime(
        string='OCR Processing Date',
        readonly=True,
    )

    def action_extract_ocr(self):
        """Extract text from document using OCR"""
        self.ensure_one()

        service = self.env['dms.ocr.extraction.service'].search(
            [('active', '=', True)], limit=1
        )
        if not service:
            raise UserError(_('No active OCR service configured. '
                            'Please configure one in Property DMS > Configuration.'))

        result = service.extract_text(self)

        if 'error' in result:
            raise UserError(_('OCR extraction failed: %s') % result['error'])

        self.write({
            'ocr_text': result.get('text', ''),
            'ocr_processed': True,
            'ocr_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('OCR Complete'),
                'message': _('Text extracted from %(pages)d page(s).') % {
                    'pages': result.get('pages', 1)
                },
                'type': 'success',
                'sticky': False,
            }
        }

    def action_ocr_and_classify(self):
        """Perform OCR extraction followed by AI classification"""
        self.ensure_one()

        # First OCR
        ocr_service = self.env['dms.ocr.extraction.service'].search(
            [('active', '=', True)], limit=1
        )
        if ocr_service:
            ocr_result = ocr_service.extract_text(self)
            if 'text' in ocr_result:
                self.write({
                    'ocr_text': ocr_result['text'],
                    'ocr_processed': True,
                    'ocr_date': fields.Datetime.now(),
                })

        # Then classify
        ai_service = self.env['dms.ai.classification.service'].search(
            [('active', '=', True)], limit=1
        )
        if ai_service:
            result = ai_service.classify_document(self)
            if 'error' not in result:
                ai_service.apply_classification(self, result)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Processing Complete'),
                'message': _('Document processed with OCR and AI classification.'),
                'type': 'success',
                'sticky': False,
            }
        }
