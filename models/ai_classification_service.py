# -*- coding: utf-8 -*-

import logging
import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AIClassificationService(models.Model):
    """AI Classification Service for Document Analysis"""

    _name = 'dms.ai.classification.service'
    _description = 'AI Document Classification Service'

    name = fields.Char(string='Service Name', required=True)
    active = fields.Boolean(default=True)

    # Provider Configuration
    provider = fields.Selection([
        ('openai', 'OpenAI (GPT-4 Vision)'),
        ('claude', 'Anthropic Claude'),
        ('azure', 'Azure Document Intelligence'),
        ('google', 'Google Document AI'),
        ('local', 'Local Model (Ollama)'),
    ], string='AI Provider', required=True, default='openai')

    api_key = fields.Char(string='API Key', groups='base.group_system')
    api_endpoint = fields.Char(string='API Endpoint')
    model_name = fields.Char(string='Model Name', default='gpt-4-vision-preview')

    # Classification Settings
    confidence_threshold = fields.Float(
        string='Confidence Threshold',
        default=0.75,
        help='Minimum confidence score to auto-apply classification',
    )

    auto_tag = fields.Boolean(
        string='Auto-Tag Documents',
        default=True,
        help='Automatically apply tags based on AI classification',
    )

    auto_extract = fields.Boolean(
        string='Auto-Extract Data',
        default=True,
        help='Automatically extract vendor, amount, date from invoices',
    )

    # Statistics
    documents_processed = fields.Integer(
        string='Documents Processed',
        readonly=True,
    )

    avg_confidence = fields.Float(
        string='Avg Confidence Score',
        readonly=True,
        digits=(4, 2),
    )

    last_run = fields.Datetime(string='Last Run', readonly=True)

    def _get_classification_prompt(self):
        """Return the classification prompt for AI"""
        return """Analyze this document image and classify it. Return JSON with:
{
    "document_type": "invoice|contract|certificate|correspondence|tax|medical|id_document|other",
    "sub_type": "specific type within category",
    "language": "de|en|other",
    "confidence": 0.0-1.0,
    "extracted_data": {
        "vendor_name": "if applicable",
        "amount": "numeric value if found",
        "currency": "EUR|USD|etc",
        "date": "YYYY-MM-DD if found",
        "reference": "invoice/contract number if found"
    },
    "suggested_tags": ["list", "of", "relevant", "tags"],
    "sensitivity": "public|internal|confidential|restricted",
    "retention_years": "suggested retention period based on German law"
}

German document types to detect:
- Rechnung (Invoice)
- Vertrag (Contract)
- Kontoauszug (Bank Statement)
- Steuerbescheid (Tax Notice)
- Mietvertrag (Lease Agreement)
- Versicherungspolice (Insurance Policy)
- Lohnabrechnung (Payroll)
- Bewerbung (Application)
"""

    def classify_document(self, document):
        """Classify a single document using AI"""
        self.ensure_one()

        if not document.attachment_ids:
            return {'error': 'No attachment found'}

        attachment = document.attachment_ids[0]

        # Get document content
        if attachment.mimetype and attachment.mimetype.startswith('image/'):
            content = base64.b64encode(attachment.raw).decode('utf-8')
            content_type = 'image'
        elif attachment.mimetype == 'application/pdf':
            # For PDF, we'd need OCR first
            content = attachment.raw
            content_type = 'pdf'
        else:
            content = attachment.raw
            content_type = 'text'

        try:
            if self.provider == 'openai':
                result = self._classify_openai(content, content_type)
            elif self.provider == 'claude':
                result = self._classify_claude(content, content_type)
            elif self.provider == 'azure':
                result = self._classify_azure(content, content_type)
            elif self.provider == 'local':
                result = self._classify_local(content, content_type)
            else:
                result = {'error': f'Provider {self.provider} not implemented'}

            # Update statistics
            self.sudo().write({
                'documents_processed': self.documents_processed + 1,
                'last_run': fields.Datetime.now(),
            })

            return result

        except Exception as e:
            _logger.error(f"AI Classification error: {str(e)}")
            return {'error': str(e)}

    def _classify_openai(self, content, content_type):
        """Classify using OpenAI GPT-4 Vision"""
        try:
            import openai
        except ImportError:
            return {'error': 'openai package not installed'}

        client = openai.OpenAI(api_key=self.api_key)

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": self._get_classification_prompt()},
            ]
        }]

        if content_type == 'image':
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{content}"}
            })

        response = client.chat.completions.create(
            model=self.model_name or "gpt-4-vision-preview",
            messages=messages,
            max_tokens=1000,
        )

        import json
        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            return {'raw_response': response.choices[0].message.content}

    def _classify_claude(self, content, content_type):
        """Classify using Anthropic Claude"""
        try:
            import anthropic
        except ImportError:
            return {'error': 'anthropic package not installed'}

        client = anthropic.Anthropic(api_key=self.api_key)

        message_content = [{"type": "text", "text": self._get_classification_prompt()}]

        if content_type == 'image':
            message_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": content,
                }
            })

        response = client.messages.create(
            model=self.model_name or "claude-3-sonnet-20240229",
            max_tokens=1000,
            messages=[{"role": "user", "content": message_content}]
        )

        import json
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {'raw_response': response.content[0].text}

    def _classify_azure(self, content, content_type):
        """Classify using Azure Document Intelligence"""
        # Placeholder for Azure implementation
        return {'error': 'Azure integration pending'}

    def _classify_local(self, content, content_type):
        """Classify using local Ollama model"""
        try:
            import requests
        except ImportError:
            return {'error': 'requests package not installed'}

        endpoint = self.api_endpoint or 'http://localhost:11434/api/generate'

        response = requests.post(endpoint, json={
            'model': self.model_name or 'llava',
            'prompt': self._get_classification_prompt(),
            'images': [content] if content_type == 'image' else [],
            'stream': False,
        })

        import json
        try:
            result = response.json()
            return json.loads(result.get('response', '{}'))
        except (json.JSONDecodeError, KeyError):
            return {'raw_response': response.text}

    def apply_classification(self, document, classification):
        """Apply classification results to document"""
        self.ensure_one()

        if 'error' in classification:
            return False

        confidence = classification.get('confidence', 0)
        if confidence < self.confidence_threshold:
            _logger.info(f"Confidence {confidence} below threshold {self.confidence_threshold}")
            return False

        values = {}

        # Set extraction confidence
        values['extraction_confidence'] = confidence

        # Apply extracted data
        extracted = classification.get('extracted_data', {})
        if extracted.get('vendor_name'):
            values['extracted_vendor'] = extracted['vendor_name']
        if extracted.get('amount'):
            try:
                values['extracted_amount'] = float(str(extracted['amount']).replace(',', '.'))
            except (ValueError, TypeError):
                pass
        if extracted.get('date'):
            values['extracted_date'] = extracted['date']
        if extracted.get('reference'):
            values['extracted_reference'] = extracted['reference']

        # Set document type flags
        doc_type = classification.get('document_type', '')
        if doc_type == 'invoice':
            values['is_invoice'] = True
            values['invoice_state'] = 'pending'

        # Set sensitivity
        sensitivity_map = {
            'public': 'public',
            'internal': 'internal',
            'confidential': 'confidential',
            'restricted': 'restricted',
        }
        if classification.get('sensitivity') in sensitivity_map:
            values['sensitivity'] = sensitivity_map[classification['sensitivity']]

        # Apply tags if auto_tag enabled
        if self.auto_tag and classification.get('suggested_tags'):
            tag_ids = self._get_or_create_tags(classification['suggested_tags'])
            if tag_ids:
                values['tag_ids'] = [(4, tid) for tid in tag_ids]

        if values:
            document.write(values)
            return True

        return False

    def _get_or_create_tags(self, tag_names):
        """Get existing tags or create new ones"""
        Tag = self.env['documents.tag']
        tag_ids = []

        for name in tag_names[:5]:  # Limit to 5 tags
            tag = Tag.search([('name', 'ilike', name)], limit=1)
            if tag:
                tag_ids.append(tag.id)
            # Don't auto-create tags - only use existing ones

        return tag_ids


class AIClassificationLog(models.Model):
    """Log of AI classification results"""

    _name = 'dms.ai.classification.log'
    _description = 'AI Classification Log'
    _order = 'create_date desc'

    document_id = fields.Many2one(
        'documents.document',
        string='Document',
        required=True,
        ondelete='cascade',
    )

    service_id = fields.Many2one(
        'dms.ai.classification.service',
        string='AI Service',
        required=True,
    )

    classification_result = fields.Text(string='Raw Result')
    confidence = fields.Float(string='Confidence Score')
    document_type = fields.Char(string='Detected Type')
    applied = fields.Boolean(string='Applied to Document')
    error_message = fields.Text(string='Error')
    processing_time = fields.Float(string='Processing Time (s)')
