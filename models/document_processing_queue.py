# -*- coding: utf-8 -*-

import logging
import time
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DocumentProcessingQueue(models.Model):
    """Queue for batch document processing with AI classification"""

    _name = 'dms.document.processing.queue'
    _description = 'Document Processing Queue'
    _order = 'priority desc, create_date asc'

    name = fields.Char(
        string='Reference',
        required=True,
        default=lambda self: _('New'),
        readonly=True,
    )

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

    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True)

    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1')

    attempts = fields.Integer(string='Attempts', default=0, readonly=True)
    max_attempts = fields.Integer(string='Max Attempts', default=3)

    scheduled_date = fields.Datetime(
        string='Scheduled Date',
        default=fields.Datetime.now,
    )

    started_date = fields.Datetime(string='Started', readonly=True)
    completed_date = fields.Datetime(string='Completed', readonly=True)

    result_message = fields.Text(string='Result Message', readonly=True)
    error_message = fields.Text(string='Error Message', readonly=True)

    log_id = fields.Many2one(
        'dms.ai.classification.log',
        string='Classification Log',
        readonly=True,
    )

    # Related fields for display
    document_name = fields.Char(
        related='document_id.name',
        string='Document Name',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dms.document.processing.queue'
                ) or _('New')
        return super().create(vals_list)

    def action_process(self):
        """Process this queue item immediately"""
        self.ensure_one()
        if self.state not in ['pending', 'failed']:
            return

        self.write({
            'state': 'processing',
            'started_date': fields.Datetime.now(),
            'attempts': self.attempts + 1,
        })

        start_time = time.time()

        try:
            # Perform AI classification
            result = self.service_id.classify_document(self.document_id)

            processing_time = time.time() - start_time

            # Create log entry
            log_vals = {
                'document_id': self.document_id.id,
                'service_id': self.service_id.id,
                'processing_time': processing_time,
            }

            if 'error' in result:
                log_vals.update({
                    'error_message': result['error'],
                    'applied': False,
                })
                self.write({
                    'state': 'failed' if self.attempts >= self.max_attempts else 'pending',
                    'error_message': result['error'],
                    'scheduled_date': fields.Datetime.now() + timedelta(minutes=5 * self.attempts),
                })
            else:
                # Apply classification to document
                applied = self.service_id.apply_classification(
                    self.document_id, result
                )

                log_vals.update({
                    'classification_result': str(result),
                    'confidence': result.get('confidence', 0),
                    'document_type': result.get('document_type', ''),
                    'applied': applied,
                })

                self.write({
                    'state': 'done',
                    'completed_date': fields.Datetime.now(),
                    'result_message': f"Classification: {result.get('document_type', 'Unknown')} "
                                     f"(Confidence: {result.get('confidence', 0):.1%})",
                })

            log = self.env['dms.ai.classification.log'].create(log_vals)
            self.log_id = log.id

        except Exception as e:
            _logger.exception(f"Queue processing error: {e}")
            self.write({
                'state': 'failed' if self.attempts >= self.max_attempts else 'pending',
                'error_message': str(e),
                'scheduled_date': fields.Datetime.now() + timedelta(minutes=5 * self.attempts),
            })

    def action_cancel(self):
        """Cancel this queue item"""
        self.write({'state': 'cancelled'})

    def action_retry(self):
        """Retry failed queue item"""
        self.write({
            'state': 'pending',
            'attempts': 0,
            'error_message': False,
            'scheduled_date': fields.Datetime.now(),
        })

    @api.model
    def _cron_process_queue(self, limit=10):
        """Cron job to process pending queue items"""
        items = self.search([
            ('state', '=', 'pending'),
            ('scheduled_date', '<=', fields.Datetime.now()),
        ], limit=limit, order='priority desc, scheduled_date asc')

        _logger.info(f"Processing {len(items)} queue items")

        for item in items:
            try:
                item.action_process()
                self.env.cr.commit()  # Commit after each item
            except Exception as e:
                _logger.exception(f"Cron processing error for {item.name}: {e}")
                self.env.cr.rollback()

        return True

    @api.model
    def add_documents_to_queue(self, document_ids, service_id, priority='1'):
        """Add multiple documents to processing queue"""
        if not service_id:
            # Get default service
            service = self.env['dms.ai.classification.service'].search(
                [('active', '=', True)], limit=1
            )
            if not service:
                raise UserError(_('No active AI classification service configured.'))
            service_id = service.id

        queue_items = []
        for doc_id in document_ids:
            # Check if already in queue
            existing = self.search([
                ('document_id', '=', doc_id),
                ('state', 'in', ['pending', 'processing']),
            ], limit=1)
            if not existing:
                queue_items.append({
                    'document_id': doc_id,
                    'service_id': service_id,
                    'priority': priority,
                })

        if queue_items:
            return self.create(queue_items)
        return self.browse()


class DocumentsDocumentAI(models.Model):
    """Extend documents.document with AI classification actions"""

    _inherit = 'documents.document'

    ai_classification_count = fields.Integer(
        string='Classification Count',
        compute='_compute_ai_classification_count',
    )

    def _compute_ai_classification_count(self):
        Log = self.env['dms.ai.classification.log']
        for doc in self:
            doc.ai_classification_count = Log.search_count([
                ('document_id', '=', doc.id)
            ])

    def action_classify_ai(self):
        """Classify this document using AI"""
        self.ensure_one()

        service = self.env['dms.ai.classification.service'].search(
            [('active', '=', True)], limit=1
        )
        if not service:
            raise UserError(_('No active AI classification service configured. '
                            'Please configure one in Property DMS > Configuration > AI Classification.'))

        result = service.classify_document(self)

        if 'error' in result:
            raise UserError(_('Classification failed: %s') % result['error'])

        # Log the result
        self.env['dms.ai.classification.log'].create({
            'document_id': self.id,
            'service_id': service.id,
            'classification_result': str(result),
            'confidence': result.get('confidence', 0),
            'document_type': result.get('document_type', ''),
            'applied': False,  # Will be set below
        })

        # Apply if above threshold
        applied = service.apply_classification(self, result)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Classification'),
                'message': _('Document classified as: %(type)s (%(conf).1f%% confidence). %(applied)s') % {
                    'type': result.get('document_type', 'Unknown'),
                    'conf': result.get('confidence', 0) * 100,
                    'applied': _('Applied to document.') if applied else _('Below confidence threshold.'),
                },
                'type': 'success' if applied else 'warning',
                'sticky': False,
            }
        }

    def action_add_to_queue(self):
        """Add selected documents to AI processing queue"""
        Queue = self.env['dms.document.processing.queue']
        items = Queue.add_documents_to_queue(self.ids, None)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Processing Queue'),
                'message': _('%d document(s) added to processing queue.') % len(items),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_ai_logs(self):
        """View AI classification logs for this document"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Classification History'),
            'res_model': 'dms.ai.classification.log',
            'view_mode': 'list,form',
            'domain': [('document_id', '=', self.id)],
            'context': {'default_document_id': self.id},
        }
