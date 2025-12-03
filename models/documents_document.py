# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class DocumentsDocument(models.Model):
    """Extend documents.document with property management fields"""

    _inherit = 'documents.document'

    # === SENSITIVITY CLASSIFICATION ===
    sensitivity = fields.Selection([
        ('public', 'Public (oeffentlich)'),
        ('internal', 'Internal (intern)'),
        ('confidential', 'Confidential (vertraulich)'),
        ('restricted', 'Restricted (streng-vertraulich)'),
    ], string='Sensitivity', default='internal', tracking=True,
       help='Document sensitivity level for backup and access control')

    # === SOURCE TRACKING ===
    document_source = fields.Selection([
        ('scan', 'Scanned Document'),
        ('email', 'Email Attachment'),
        ('portal', 'Portal Upload'),
        ('upload', 'Manual Upload'),
        ('generated', 'System Generated'),
        ('import', 'Bulk Import'),
    ], string='Source', default='upload', tracking=True)

    # === RETENTION ===
    retention_policy_id = fields.Many2one(
        'documents.retention.policy',
        string='Retention Policy',
        tracking=True,
    )

    retention_date = fields.Date(
        string='Retention Until',
        compute='_compute_retention_date',
        store=True,
        help='Date until this document must be retained',
    )

    retention_action_due = fields.Boolean(
        string='Retention Action Due',
        compute='_compute_retention_action_due',
        store=True,
    )

    # === DOCUMENT DATE ===
    document_date = fields.Date(
        string='Document Date',
        help='Date of the document (invoice date, contract date, etc.)',
        tracking=True,
    )

    fiscal_year = fields.Char(
        string='Fiscal Year',
        compute='_compute_fiscal_year',
        store=True,
    )

    # === AI READINESS ===
    extracted_vendor = fields.Char(
        string='Extracted Vendor',
        help='Vendor name extracted by AI/OCR',
    )

    extracted_amount = fields.Monetary(
        string='Extracted Amount',
        currency_field='currency_id',
        help='Amount extracted by AI/OCR',
    )

    extracted_date = fields.Date(
        string='Extracted Date',
        help='Date extracted by AI/OCR',
    )

    extracted_reference = fields.Char(
        string='Extracted Reference',
        help='Reference number extracted by AI/OCR',
    )

    extraction_confidence = fields.Float(
        string='Extraction Confidence',
        help='AI confidence score (0-1)',
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends('document_date', 'retention_policy_id', 'retention_policy_id.retention_years',
                 'retention_policy_id.retention_months', 'retention_policy_id.retention_trigger')
    def _compute_retention_date(self):
        """Calculate retention date based on policy"""
        from dateutil.relativedelta import relativedelta
        for doc in self:
            if not doc.retention_policy_id:
                doc.retention_date = False
                continue

            policy = doc.retention_policy_id
            trigger_date = False

            if policy.retention_trigger == 'creation':
                trigger_date = doc.create_date.date() if doc.create_date else False
            elif policy.retention_trigger == 'document_date':
                trigger_date = doc.document_date
            elif policy.retention_trigger == 'fiscal_year_end':
                if doc.document_date:
                    trigger_date = doc.document_date.replace(month=12, day=31)

            if trigger_date:
                doc.retention_date = trigger_date + relativedelta(
                    years=policy.retention_years,
                    months=policy.retention_months
                )
            else:
                doc.retention_date = False

    @api.depends('retention_date')
    def _compute_retention_action_due(self):
        """Check if retention action is due"""
        today = fields.Date.today()
        for doc in self:
            doc.retention_action_due = bool(
                doc.retention_date and doc.retention_date <= today
            )

    @api.depends('document_date')
    def _compute_fiscal_year(self):
        """Extract fiscal year from document date"""
        for doc in self:
            doc.fiscal_year = str(doc.document_date.year) if doc.document_date else False

    # === ENTITY LINKING ===
    # Property linking
    property_id = fields.Many2one(
        'res.partner',
        string='Property',
        domain="[('is_company', '=', True)]",
        tracking=True,
        help='Link to property (as company partner)',
    )

    # Tenant linking
    tenant_id = fields.Many2one(
        'res.partner',
        string='Tenant',
        tracking=True,
        help='Link to tenant contact',
    )

    # Invoice linking
    linked_invoice_id = fields.Many2one(
        'account.move',
        string='Linked Invoice',
        domain="[('move_type', 'in', ['in_invoice', 'out_invoice'])]",
        tracking=True,
    )

    # === INVOICE STATE ===
    is_invoice = fields.Boolean(
        string='Is Invoice Document',
        default=False,
    )

    invoice_state = fields.Selection([
        ('none', 'Not an Invoice'),
        ('pending', 'Pending Processing'),
        ('linked', 'Linked to Invoice'),
        ('duplicate', 'Duplicate Detected'),
    ], string='Invoice State', default='none', tracking=True)

    # === DUPLICATE DETECTION ===
    duplicate_of_id = fields.Many2one(
        'documents.document',
        string='Duplicate Of',
        help='If this is a duplicate, reference to original',
    )

    is_duplicate = fields.Boolean(
        string='Is Duplicate',
        compute='_compute_is_duplicate',
        store=True,
    )

    @api.depends('duplicate_of_id')
    def _compute_is_duplicate(self):
        for doc in self:
            doc.is_duplicate = bool(doc.duplicate_of_id)

    def action_check_duplicate_invoice(self):
        """Check if this invoice document is a duplicate"""
        self.ensure_one()
        if not self.extracted_amount or not self.extracted_vendor:
            return

        # Search for similar invoices
        domain = [
            ('id', '!=', self.id),
            ('extracted_vendor', 'ilike', self.extracted_vendor),
            ('extracted_amount', '=', self.extracted_amount),
        ]
        if self.extracted_date:
            domain.append(('extracted_date', '=', self.extracted_date))

        duplicates = self.search(domain, limit=1)
        if duplicates:
            self.write({
                'invoice_state': 'duplicate',
                'duplicate_of_id': duplicates[0].id,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Duplicate Found'),
                    'message': _('This document appears to be a duplicate of %s') % duplicates[0].name,
                    'type': 'warning',
                }
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('No Duplicate'),
                'message': _('No duplicate invoice found'),
                'type': 'success',
            }
        }
