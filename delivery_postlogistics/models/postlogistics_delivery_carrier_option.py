# Copyright 2013-2016 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DeliveryCarrierOption(models.Model):
    """ Set name translatable and add service group """

    _name = "postlogistics.delivery.carrier.option"
    _description = "Delivery carrier option"
    _inherits = {"postlogistics.delivery.carrier.template.option": "tmpl_option_id"}

    active = fields.Boolean(default=True)
    mandatory = fields.Boolean(
        help="If checked, this option is necessarily applied " "to the delivery order"
    )
    by_default = fields.Boolean(
        string="Applied by Default",
        help="By check, user can choose to apply this option "
        "to each Delivery Order\n using this delivery method",
    )
    tmpl_option_id = fields.Many2one(
        comodel_name="postlogistics.delivery.carrier.template.option",
        string="Option",
        required=True,
        ondelete="cascade",
    )
    carrier_id = fields.Many2one(comodel_name="delivery.carrier", string="Carrier")
    readonly_flag = fields.Boolean(
        string="Readonly Flag",
        help="When True, help to prevent the user to modify some fields "
        "option (if attribute is defined in the view)",
    )

    name = fields.Char(translate=True, required=True)

    allowed_postlogistics_tmpl_options_ids = fields.Many2many(
        "postlogistics.delivery.carrier.template.option",
        compute="_compute_allowed_postlogistics_tmpl_options_ids",
        store=False,
    )

    @api.depends("carrier_id.allowed_postlogistics_tmpl_options_ids")
    def _compute_allowed_postlogistics_tmpl_options_ids(self):
        """ Gets the available template options from related delivery.carrier
            (be it from cache or context)."""
        for option in self:
            defaults = self.env.context.get(
                "default_allowed_postlogistics_tmpl_options_ids"
            )
            option.allowed_postlogistics_tmpl_options_ids = (
                option.carrier_id.allowed_postlogistics_tmpl_options_ids
                or defaults
                or False
            )
