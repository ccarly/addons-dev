# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import UserError


class FleetRentalCreateInvoiceWizard(models.TransientModel):
    _name = "fleet_rental.create_invoice_wizard"

    amount = fields.Float('Payment Amount', digits=dp.get_precision('Account'),
                          help="The amount to be invoiced.")
    product_id = fields.Many2one('product.product', string='Payment Product',
                                 readonly=True)
    type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Refund'),
        ('in_refund', 'Vendor Refund'),
        ], readonly=True, index=True,
        default=lambda self: self._context.get('type', 'out_invoice'))

    @api.multi
    def _create_invoice(self, document, amount):
        self.ensure_one()
        inv_obj = self.env['account.invoice']

        account_id = False
        if self.product_id.id:
            account_id = self.product_id.property_account_income_id.id
        if not account_id:
            raise UserError(
                _('There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                (self.product_id.name,))

        if self.amount <= 0.00:
            raise UserError(_('The value of the payment amount must be positive.'))

        amount = self.amount

        if not document.analytic_account_id:
            document.document_id.analytic_account_id = self.env['account.analytic.account'].sudo().create({'name': document.name + '_' + document.create_date, 'partner_id': document.partner_id.id}).id

        invoice = inv_obj.create({
            'name': document.name,
            'origin': document.name,
            'type': self.type,
            'reference': False,
            'account_id': document.partner_id.property_account_receivable_id.id,
            'partner_id': document.partner_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': self.product_id.name,
                'origin': document.name,
                'account_id': account_id,
                'price_unit': amount,
                'quantity': 1.0,
                'discount': 0.0,
                'uom_id': self.product_id.uom_id.id,
                'product_id': self.product_id.id,
                'fleet_rental_document_id': document.document_id.id,
                'account_analytic_id': document.document_id.analytic_account_id.id,
            })],
        })
        return invoice

    @api.multi
    def create_invoices(self):
        documents = self.env[self._context.get('active_model')].browse(self._context.get('active_ids', []))

        # Create product if necessary
        if not self.product_id:
            self.product_id = self._create_product()

        for document in documents:
            amount = self.amount
            self._create_invoice(document, amount)

        if self._context.get('open_invoices', False):
            return documents.action_view_invoice()
        return {'type': 'ir.actions.act_window_close'}

    def _create_product(self):
        model = self._context.get('active_model')
        name = 'Rent payment' if model == 'fleet_rental.document_return' \
               else "Down payment"
        name = name + ' ' + self.env.user.branch_id.name
        account_income_id = self.env.user.branch_id.rental_account_id.id \
            if model == 'fleet_rental.document_return' else \
            self.env.user.branch_id.deposit_account_id.id
        vals = {
            'name': name,
            'type': 'service',
            'invoice_policy': 'order',
            'property_account_income_id': account_income_id,
        }
        product = self.env['product.product'].create(vals)
        if model == 'fleet_rental.document_return':
            self.env.user.branch_id.rental_product_id = product.id
        else:
            self.env.user.branch_id.deposit_product_id = product.id
        return product
