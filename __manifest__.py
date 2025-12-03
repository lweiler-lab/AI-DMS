{
    'name': 'DMS Property Integration',
    'version': '19.0.3.0.1',
    'category': 'Document Management',
    'summary': 'Document Management with Retention Policies for Real Estate',
    'description': """
DMS Property Integration
========================

AI-assisted Document Management System for real estate:

* Retention Policies (German Legal Compliance)
  - AO §147: 10 years for accounting documents
  - HGB §257: 10 years for business records
  - DSGVO: Data minimization requirements
  - AGG §15: 6 months for applications

* Tag Taxonomy (7 Dimensions)
  - Person: tenant, owner, vendor
  - Document Type: invoice, contract, certificate
  - Property: property assignment
  - Time Period: year, quarter, month
  - Status: draft, active, archived
  - Source: scan, email, portal, upload
  - Sensitivity: public, internal, confidential, restricted

* Workspace Structure
  - Immobilien (Real Estate)
  - Geschaeftlich (Business)
  - Persoenlich (Personal)
  - Steuern (Tax)

* Document Linking
  - Properties, Units, Tenants
  - Contracts, Invoices
  - Billing Periods
    """,
    'author': 'Syntax & Sabotage Consulting',
    'website': 'https://syntaxandsabotage.io',
    'depends': ['base', 'mail', 'documents', 'account'],
    'data': [
        'security/dms_property_security.xml',
        'security/ir.model.access.csv',
        'data/retention_policies.xml',
        'data/tag_taxonomy.xml',
        'views/retention_policy_views.xml',
        'views/documents_document_views.xml',
        'views/dms_property_menus.xml',
    ],
    'assets': {},
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
