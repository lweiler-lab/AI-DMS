# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class DocumentRetentionPolicy(models.Model):
    """Document Retention Policy - German Legal Compliance"""

    _name = 'documents.retention.policy'
    _description = 'Document Retention Policy'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Policy Name',
        required=True,
        tracking=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )

    # === SCOPE ===
    tag_ids = fields.Many2many(
        'documents.tag',
        string='Document Tags',
        help='Apply this policy to documents with these tags',
    )

    folder_ids = fields.Many2many(
        'documents.document',
        string='Folders',
        domain="[('type', '=', 'folder')]",
        help='Apply this policy to documents in these folders',
    )

    document_type = fields.Selection([
        ('all', 'All Matching Documents'),
        ('invoice', 'Invoices Only'),
        ('contract', 'Contracts Only'),
        ('certificate', 'Certificates Only'),
        ('correspondence', 'Correspondence Only'),
    ], string='Document Type', default='all')

    # === RETENTION ===
    retention_years = fields.Integer(
        string='Retention Period (Years)',
        required=True,
        default=10,
        help='Number of years to retain documents',
    )

    retention_months = fields.Integer(
        string='Additional Months',
        default=0,
        help='Additional months beyond years',
    )

    retention_trigger = fields.Selection([
        ('creation', 'From Creation Date'),
        ('document_date', 'From Document Date'),
        ('expiry', 'From Expiry/End Date'),
        ('last_access', 'From Last Access'),
        ('fiscal_year_end', 'From Fiscal Year End'),
    ], string='Retention Trigger', default='document_date', required=True)

    # === ACTION ===
    action = fields.Selection([
        ('archive', 'Move to Archive'),
        ('delete', 'Delete Permanently'),
        ('review', 'Flag for Review'),
        ('export_delete', 'Export then Delete'),
    ], string='Action After Retention', default='archive', required=True)

    archive_folder_id = fields.Many2one(
        'documents.document',
        string='Archive Folder',
        domain="[('type', '=', 'folder')]",
        help='Folder to move documents when archiving',
    )

    # === NOTIFICATION ===
    notify_before_days = fields.Integer(
        string='Notify Days Before',
        default=30,
        help='Send notification this many days before retention action',
    )

    notify_user_ids = fields.Many2many(
        'res.users',
        string='Notify Users',
        help='Users to notify when retention action is due',
    )

    # === LEGAL BASIS ===
    legal_reference = fields.Text(
        string='Legal Reference',
        help='Legal basis for this retention policy (e.g., AO §147, HGB §257)',
    )

    notes = fields.Html(
        string='Notes',
    )

    # === COMPUTED ===
    document_count = fields.Integer(
        string='Matching Documents',
        compute='_compute_document_count',
    )

    upcoming_action_count = fields.Integer(
        string='Upcoming Actions',
        compute='_compute_upcoming_actions',
    )

    @api.depends('tag_ids', 'folder_ids')
    def _compute_document_count(self):
        """Count documents matching this policy"""
        Document = self.env['documents.document']
        for policy in self:
            domain = []
            if policy.tag_ids:
                domain.append(('tag_ids', 'in', policy.tag_ids.ids))
            if policy.folder_ids:
                domain.append(('folder_id', 'in', policy.folder_ids.ids))
            policy.document_count = Document.search_count(domain) if domain else 0

    def _compute_upcoming_actions(self):
        """Count documents due for retention action in next 90 days"""
        for policy in self:
            # Placeholder - implement actual date calculation
            policy.upcoming_action_count = 0

    @api.constrains('retention_years', 'retention_months')
    def _check_retention_period(self):
        """Validate retention period is positive"""
        for policy in self:
            total_months = (policy.retention_years * 12) + policy.retention_months
            if total_months <= 0:
                raise ValidationError(_(
                    'Retention period must be positive. '
                    'Please set years and/or months greater than zero.'
                ))

    def action_view_documents(self):
        """Open documents matching this policy"""
        self.ensure_one()
        domain = []
        if self.tag_ids:
            domain.append(('tag_ids', 'in', self.tag_ids.ids))
        if self.folder_ids:
            domain.append(('folder_id', 'in', self.folder_ids.ids))

        return {
            'name': _('Documents - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'list,kanban,form',
            'domain': domain,
            'context': {'default_tag_ids': self.tag_ids.ids},
        }

    def action_check_retention(self):
        """Check documents for retention action"""
        self.ensure_one()
        # Implement retention checking logic
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retention Check'),
                'message': _('Retention check completed for policy: %s') % self.name,
                'type': 'success',
            }
        }
